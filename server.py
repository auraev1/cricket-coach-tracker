import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from wsgiref.simple_server import make_server

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DB_PATH", BASE_DIR / "cricket_coach.db"))
SESSION_COOKIE = "coach_session"


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS academies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS coaches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                academy_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL DEFAULT 'Assistant Coach',
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                academy_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                age_group TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                academy_id INTEGER NOT NULL,
                coach_id INTEGER NOT NULL,
                team_id INTEGER,
                name TEXT NOT NULL,
                age INTEGER,
                primary_role TEXT NOT NULL,
                level TEXT NOT NULL,
                bowling_style TEXT,
                bowling_arm TEXT,
                batting_hand TEXT,
                batting_position TEXT,
                batting_style TEXT,
                secondary_skill TEXT,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE CASCADE,
                FOREIGN KEY(coach_id) REFERENCES coaches(id) ON DELETE CASCADE,
                FOREIGN KEY(team_id) REFERENCES teams(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS performances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                academy_id INTEGER NOT NULL,
                coach_id INTEGER NOT NULL,
                player_id INTEGER NOT NULL,
                session_date TEXT NOT NULL,
                session_type TEXT NOT NULL,
                runs INTEGER NOT NULL DEFAULT 0,
                balls_faced INTEGER NOT NULL DEFAULT 0,
                wickets INTEGER NOT NULL DEFAULT 0,
                overs REAL NOT NULL DEFAULT 0,
                runs_conceded INTEGER NOT NULL DEFAULT 0,
                dismissals INTEGER NOT NULL DEFAULT 0,
                coach_rating INTEGER NOT NULL DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(academy_id) REFERENCES academies(id) ON DELETE CASCADE,
                FOREIGN KEY(coach_id) REFERENCES coaches(id) ON DELETE CASCADE,
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                coach_id INTEGER NOT NULL,
                token TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(coach_id) REFERENCES coaches(id) ON DELETE CASCADE
            );
            """
        )

        ensure_column(connection, "players", "academy_id INTEGER")
        ensure_column(connection, "players", "coach_id INTEGER")
        ensure_column(connection, "players", "team_id INTEGER")
        ensure_column(connection, "performances", "academy_id INTEGER")
        ensure_column(connection, "performances", "coach_id INTEGER")
        ensure_column(connection, "coaches", "role TEXT NOT NULL DEFAULT 'Assistant Coach'")


def ensure_column(connection, table_name, column_definition):
    column_name = column_definition.split()[0]
    columns = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    existing = {row["name"] for row in columns}
    if columns and column_name not in existing:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_definition}")


def json_response(start_response, payload, status="200 OK", cookies=None):
    data = json.dumps(payload).encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(data))),
    ]
    for cookie in cookies or []:
        headers.append(("Set-Cookie", cookie))
    start_response(status, headers)
    return [data]


def text_response(start_response, text, status="200 OK", content_type="text/plain; charset=utf-8"):
    data = text.encode("utf-8")
    headers = [("Content-Type", content_type), ("Content-Length", str(len(data)))]
    start_response(status, headers)
    return [data]


def downloadable_response(start_response, text, filename, content_type):
    data = text.encode("utf-8")
    headers = [
        ("Content-Type", content_type),
        ("Content-Length", str(len(data))),
        ("Content-Disposition", f'attachment; filename="{filename}"'),
    ]
    start_response("200 OK", headers)
    return [data]


def no_content_response(start_response, cookies=None):
    headers = [("Content-Length", "0")]
    for cookie in cookies or []:
        headers.append(("Set-Cookie", cookie))
    start_response("204 No Content", headers)
    return [b""]


def read_json(environ):
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = 0

    raw = environ["wsgi.input"].read(length) if length else b"{}"
    return json.loads(raw.decode("utf-8") or "{}")


def row_to_dict(row):
    return {key: row[key] for key in row.keys()}


def get_cookies(environ):
    cookies = {}
    raw_cookie = environ.get("HTTP_COOKIE", "")
    if not raw_cookie:
        return cookies

    for item in raw_cookie.split(";"):
        if "=" not in item:
            continue
        key, value = item.strip().split("=", 1)
        cookies[key] = value

    return cookies


def hash_password(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    ).hex()


def create_session_cookie(token, expires_at):
    expires = datetime.fromisoformat(expires_at).strftime("%a, %d %b %Y %H:%M:%S GMT")
    return (
        f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Expires={expires}"
    )


def expired_session_cookie():
    return (
        f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; "
        "Expires=Thu, 01 Jan 1970 00:00:00 GMT"
    )


def current_coach(environ):
    token = get_cookies(environ).get(SESSION_COOKIE)
    if not token:
        raise PermissionError("Please log in first.")

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                c.id,
                c.academy_id,
                c.name,
                c.email,
                c.role,
                a.name AS academy_name,
                s.token,
                s.expires_at
            FROM sessions s
            JOIN coaches c ON c.id = s.coach_id
            JOIN academies a ON a.id = c.academy_id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()

    if row is None:
        raise PermissionError("Session not found. Please log in again.")

    if datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
        with get_connection() as connection:
            connection.execute("DELETE FROM sessions WHERE token = ?", (token,))
        raise PermissionError("Session expired. Please log in again.")

    return row_to_dict(row)


def register_coach(payload):
    coach_name = str(payload.get("coach_name", "")).strip()
    academy_name = str(payload.get("academy_name", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))

    if not coach_name or not academy_name or not email or not password:
        raise ValueError("Coach name, academy name, email, and password are required.")

    salt = secrets.token_hex(16)
    password_hash = hash_password(password, salt)

    requested_role = str(payload.get("role", "")).strip() or "Assistant Coach"
    with get_connection() as connection:
        existing_academy = connection.execute(
            "SELECT id FROM academies WHERE LOWER(name) = LOWER(?)",
            (academy_name,),
        ).fetchone()

        if existing_academy:
            academy_id = existing_academy["id"]
        else:
            academy_id = connection.execute(
                "INSERT INTO academies (name) VALUES (?)",
                (academy_name,),
            ).lastrowid

        existing_head = connection.execute(
            "SELECT id FROM coaches WHERE academy_id = ? LIMIT 1",
            (academy_id,),
        ).fetchone()
        role = "Head Coach" if existing_head is None else requested_role
        if role not in {"Head Coach", "Assistant Coach"}:
            raise ValueError("Role must be Head Coach or Assistant Coach.")

        connection.execute(
            """
            INSERT INTO coaches (academy_id, name, email, role, password_salt, password_hash)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (academy_id, coach_name, email, role, salt, password_hash),
        )

    return login_coach({"email": email, "password": password})


def login_coach(payload):
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    if not email or not password:
        raise ValueError("Email and password are required.")

    with get_connection() as connection:
        coach = connection.execute(
            """
            SELECT
                c.id,
                c.academy_id,
                c.name,
                c.email,
                c.role,
                c.password_salt,
                c.password_hash,
                a.name AS academy_name
            FROM coaches c
            JOIN academies a ON a.id = c.academy_id
            WHERE c.email = ?
            """,
            (email,),
        ).fetchone()

        if coach is None:
            raise PermissionError("Invalid email or password.")

        supplied_hash = hash_password(password, coach["password_salt"])
        if not hmac.compare_digest(supplied_hash, coach["password_hash"]):
            raise PermissionError("Invalid email or password.")

        token = secrets.token_urlsafe(32)
        expires_at = (datetime.utcnow() + timedelta(days=7)).replace(microsecond=0).isoformat()
        connection.execute(
            "INSERT INTO sessions (coach_id, token, expires_at) VALUES (?, ?, ?)",
            (coach["id"], token, expires_at),
        )

    return {
            "coach": {
                "id": coach["id"],
                "academy_id": coach["academy_id"],
                "name": coach["name"],
                "email": coach["email"],
                "role": coach["role"],
                "academy_name": coach["academy_name"],
            },
            "cookie": create_session_cookie(token, expires_at),
        }


def logout_coach(environ):
    token = get_cookies(environ).get(SESSION_COOKIE)
    if token:
        with get_connection() as connection:
            connection.execute("DELETE FROM sessions WHERE token = ?", (token,))
    return expired_session_cookie()


def list_teams(coach):
    require_head_coach(coach)
    return list_teams_for_academy(coach)


def list_teams_for_academy(coach):
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM teams
            WHERE academy_id = ?
            ORDER BY name COLLATE NOCASE
            """,
            (coach["academy_id"],),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def create_team(payload, coach):
    require_head_coach(coach)
    name = str(payload.get("name", "")).strip()
    age_group = str(payload.get("age_group", "")).strip()
    if not name:
        raise ValueError("Team name is required.")

    with get_connection() as connection:
        team_id = connection.execute(
            "INSERT INTO teams (academy_id, name, age_group) VALUES (?, ?, ?)",
            (coach["academy_id"], name, empty_to_none(age_group)),
        ).lastrowid

    return get_team(team_id, coach)


def delete_team(team_id, coach):
    require_head_coach(coach)
    ensure_team_exists(team_id, coach["academy_id"])
    with get_connection() as connection:
        connection.execute("DELETE FROM teams WHERE id = ?", (team_id,))


def get_team(team_id, coach):
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM teams WHERE id = ? AND academy_id = ?",
            (team_id, coach["academy_id"]),
        ).fetchone()

    if row is None:
        raise LookupError("Team not found.")
    return row_to_dict(row)


def list_players(coach):
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                p.*,
                t.name AS team_name
            FROM players p
            LEFT JOIN teams t ON t.id = p.team_id
            WHERE p.academy_id = ?
            ORDER BY p.name COLLATE NOCASE
            """,
            (coach["academy_id"],),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def create_player(payload, coach):
    validate_player(payload)
    team_id = nullable_team_id(payload.get("team_id"), coach["academy_id"])

    with get_connection() as connection:
        player_id = connection.execute(
            """
            INSERT INTO players (
                academy_id, coach_id, team_id, name, age, primary_role, level,
                bowling_style, bowling_arm, batting_hand, batting_position, batting_style,
                secondary_skill, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                coach["academy_id"],
                coach["id"],
                team_id,
                payload["name"],
                payload.get("age"),
                payload["primary_role"],
                payload["level"],
                empty_to_none(payload.get("bowling_style")),
                empty_to_none(payload.get("bowling_arm")),
                empty_to_none(payload.get("batting_hand")),
                empty_to_none(payload.get("batting_position")),
                empty_to_none(payload.get("batting_style")),
                empty_to_none(payload.get("secondary_skill")),
                empty_to_none(payload.get("notes")),
            ),
        ).lastrowid

    return get_player(player_id, coach)


def update_player(player_id, payload, coach):
    validate_player(payload)
    ensure_player_exists(player_id, coach["academy_id"])
    team_id = nullable_team_id(payload.get("team_id"), coach["academy_id"])

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE players
            SET team_id = ?, name = ?, age = ?, primary_role = ?, level = ?, bowling_style = ?,
                bowling_arm = ?, batting_hand = ?, batting_position = ?, batting_style = ?,
                secondary_skill = ?, notes = ?
            WHERE id = ? AND academy_id = ?
            """,
            (
                team_id,
                payload["name"],
                payload.get("age"),
                payload["primary_role"],
                payload["level"],
                empty_to_none(payload.get("bowling_style")),
                empty_to_none(payload.get("bowling_arm")),
                empty_to_none(payload.get("batting_hand")),
                empty_to_none(payload.get("batting_position")),
                empty_to_none(payload.get("batting_style")),
                empty_to_none(payload.get("secondary_skill")),
                empty_to_none(payload.get("notes")),
                player_id,
                coach["academy_id"],
            ),
        )

    return get_player(player_id, coach)


def delete_player(player_id, coach):
    ensure_player_exists(player_id, coach["academy_id"])
    with get_connection() as connection:
        connection.execute(
            "DELETE FROM players WHERE id = ? AND academy_id = ?",
            (player_id, coach["academy_id"]),
        )


def get_player(player_id, coach):
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                p.*,
                t.name AS team_name
            FROM players p
            LEFT JOIN teams t ON t.id = p.team_id
            WHERE p.id = ? AND p.academy_id = ?
            """,
            (player_id, coach["academy_id"]),
        ).fetchone()

    if row is None:
        raise LookupError("Player not found.")
    return row_to_dict(row)


def list_performances(coach):
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                pe.*,
                p.name AS player_name
            FROM performances pe
            JOIN players p ON p.id = pe.player_id
            WHERE pe.academy_id = ?
            ORDER BY pe.session_date DESC, pe.id DESC
            """,
            (coach["academy_id"],),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def create_performance(payload, coach):
    validate_performance(payload)
    ensure_player_exists(payload["player_id"], coach["academy_id"])

    with get_connection() as connection:
        performance_id = connection.execute(
            """
            INSERT INTO performances (
                academy_id, coach_id, player_id, session_date, session_type, runs, balls_faced,
                wickets, overs, runs_conceded, dismissals, coach_rating, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                coach["academy_id"],
                coach["id"],
                payload["player_id"],
                payload["session_date"],
                payload["session_type"],
                payload.get("runs", 0),
                payload.get("balls_faced", 0),
                payload.get("wickets", 0),
                payload.get("overs", 0),
                payload.get("runs_conceded", 0),
                payload.get("dismissals", 0),
                payload.get("coach_rating", 0),
                empty_to_none(payload.get("notes")),
            ),
        ).lastrowid

    return get_performance(performance_id, coach)


def update_performance(performance_id, payload, coach):
    validate_performance(payload)
    ensure_performance_exists(performance_id, coach["academy_id"])
    ensure_player_exists(payload["player_id"], coach["academy_id"])

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE performances
            SET player_id = ?, session_date = ?, session_type = ?, runs = ?, balls_faced = ?,
                wickets = ?, overs = ?, runs_conceded = ?, dismissals = ?, coach_rating = ?, notes = ?
            WHERE id = ? AND academy_id = ?
            """,
            (
                payload["player_id"],
                payload["session_date"],
                payload["session_type"],
                payload.get("runs", 0),
                payload.get("balls_faced", 0),
                payload.get("wickets", 0),
                payload.get("overs", 0),
                payload.get("runs_conceded", 0),
                payload.get("dismissals", 0),
                payload.get("coach_rating", 0),
                empty_to_none(payload.get("notes")),
                performance_id,
                coach["academy_id"],
            ),
        )

    return get_performance(performance_id, coach)


def delete_performance(performance_id, coach):
    ensure_performance_exists(performance_id, coach["academy_id"])
    with get_connection() as connection:
        connection.execute(
            "DELETE FROM performances WHERE id = ? AND academy_id = ?",
            (performance_id, coach["academy_id"]),
        )


def get_performance(performance_id, coach):
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                pe.*,
                p.name AS player_name
            FROM performances pe
            JOIN players p ON p.id = pe.player_id
            WHERE pe.id = ? AND pe.academy_id = ?
            """,
            (performance_id, coach["academy_id"]),
        ).fetchone()

    if row is None:
        raise LookupError("Performance entry not found.")
    return row_to_dict(row)


def build_report(months, player_id, team_id, coach):
    filters = ["pe.session_date >= date('now', ?)", "pe.academy_id = ?"]
    params = [f"-{months} months", coach["academy_id"]]

    if player_id != "all":
        filters.append("pe.player_id = ?")
        params.append(int(player_id))

    if team_id != "all":
        filters.append("p.team_id = ?")
        params.append(int(team_id))

    where_clause = " AND ".join(filters)

    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT
                p.id AS player_id,
                p.name,
                p.primary_role,
                COALESCE(t.name, 'Unassigned') AS team_name,
                COUNT(pe.id) AS entries,
                COALESCE(SUM(pe.runs), 0) AS runs,
                COALESCE(SUM(pe.balls_faced), 0) AS balls_faced,
                COALESCE(SUM(pe.wickets), 0) AS wickets,
                COALESCE(SUM(pe.overs), 0) AS overs,
                COALESCE(SUM(pe.runs_conceded), 0) AS runs_conceded,
                COALESCE(SUM(pe.dismissals), 0) AS dismissals,
                COALESCE(AVG(pe.coach_rating), 0) AS average_rating,
                (
                    SELECT latest.notes
                    FROM performances latest
                    WHERE latest.player_id = p.id
                      AND latest.academy_id = pe.academy_id
                      AND latest.session_date >= date('now', ?)
                      AND COALESCE(TRIM(latest.notes), '') <> ''
                    ORDER BY latest.session_date DESC, latest.id DESC
                    LIMIT 1
                ) AS latest_note
            FROM performances pe
            JOIN players p ON p.id = pe.player_id
            LEFT JOIN teams t ON t.id = p.team_id
            WHERE {where_clause}
            GROUP BY p.id, p.name, p.primary_role, t.name
            ORDER BY p.name COLLATE NOCASE
            """,
            [f"-{months} months", *params],
        ).fetchall()

    totals = {"runs": 0, "wickets": 0, "dismissals": 0, "average_rating": "0.0"}
    players = []
    rating_sum = 0
    entry_sum = 0

    for row in rows:
        balls_faced = row["balls_faced"] or 0
        overs = row["overs"] or 0
        runs_conceded = row["runs_conceded"] or 0
        players.append(
            {
                "id": row["player_id"],
                "name": row["name"],
                "primary_role": row["primary_role"],
                "team_name": row["team_name"],
                "entries": row["entries"],
                "runs": row["runs"],
                "wickets": row["wickets"],
                "dismissals": row["dismissals"],
                "overs": f"{overs:.1f}",
                "strike_rate": f"{(row['runs'] / balls_faced * 100):.1f}" if balls_faced else "0.0",
                "economy": f"{(runs_conceded / overs):.1f}" if overs else "0.0",
                "latest_note": row["latest_note"],
            }
        )
        totals["runs"] += row["runs"]
        totals["wickets"] += row["wickets"]
        totals["dismissals"] += row["dismissals"]
        rating_sum += row["average_rating"] * row["entries"]
        entry_sum += row["entries"]

    totals["average_rating"] = f"{(rating_sum / entry_sum):.1f}" if entry_sum else "0.0"

    return {
        "period_label": describe_period(months),
        "academy_name": coach["academy_name"],
        "total_entries": entry_sum,
        "totals": totals,
        "players": players,
    }


def list_coaches(coach):
    require_head_coach(coach)
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, name, email, role, created_at
            FROM coaches
            WHERE academy_id = ?
            ORDER BY
                CASE WHEN role = 'Head Coach' THEN 0 ELSE 1 END,
                name COLLATE NOCASE
            """,
            (coach["academy_id"],),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def create_coach(payload, coach):
    require_head_coach(coach)
    name = str(payload.get("name", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    role = str(payload.get("role", "")).strip() or "Assistant Coach"

    if not name or not email or not password:
        raise ValueError("Coach name, email, and password are required.")
    if role not in {"Head Coach", "Assistant Coach"}:
        raise ValueError("Role must be Head Coach or Assistant Coach.")
    if role == "Head Coach":
        raise ValueError("Use role update to promote a coach to Head Coach.")

    salt = secrets.token_hex(16)
    password_hash = hash_password(password, salt)

    with get_connection() as connection:
        coach_id = connection.execute(
            """
            INSERT INTO coaches (academy_id, name, email, role, password_salt, password_hash)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (coach["academy_id"], name, email, role, salt, password_hash),
        ).lastrowid
        row = connection.execute(
            "SELECT id, name, email, role, created_at FROM coaches WHERE id = ?",
            (coach_id,),
        ).fetchone()

    return row_to_dict(row)


def update_coach_role(target_coach_id, payload, coach):
    require_head_coach(coach)
    new_role = str(payload.get("role", "")).strip()
    if new_role not in {"Head Coach", "Assistant Coach"}:
        raise ValueError("Role must be Head Coach or Assistant Coach.")

    with get_connection() as connection:
        target = connection.execute(
            "SELECT id, role FROM coaches WHERE id = ? AND academy_id = ?",
            (target_coach_id, coach["academy_id"]),
        ).fetchone()

        if target is None:
            raise LookupError("Coach not found.")

        if target["id"] == coach["id"] and new_role != "Head Coach":
            raise ValueError("Head Coach cannot demote themselves.")

        if new_role == "Head Coach":
            connection.execute(
                "UPDATE coaches SET role = 'Assistant Coach' WHERE academy_id = ? AND id != ?",
                (coach["academy_id"], target_coach_id),
            )

        connection.execute(
            "UPDATE coaches SET role = ? WHERE id = ? AND academy_id = ?",
            (new_role, target_coach_id, coach["academy_id"]),
        )

        row = connection.execute(
            "SELECT id, name, email, role, created_at FROM coaches WHERE id = ?",
            (target_coach_id,),
        ).fetchone()

    return row_to_dict(row)


def require_head_coach(coach):
    if coach["role"] != "Head Coach":
        raise PermissionError("Only the Head Coach can perform this action.")


def describe_period(months):
    labels = {1: "Last 1 month", 3: "Last 3 months", 6: "Last 6 months", 12: "Last 12 months"}
    return labels.get(months, f"Last {months} months")


def build_report_csv(report):
    rows = [
        ["Academy", report["academy_name"]],
        ["Period", report["period_label"]],
        [],
        ["Total Entries", report["total_entries"]],
        ["Total Runs", report["totals"]["runs"]],
        ["Total Wickets", report["totals"]["wickets"]],
        ["Dismissals", report["totals"]["dismissals"]],
        ["Average Rating", report["totals"]["average_rating"]],
        [],
        [
            "Player",
            "Team",
            "Role",
            "Entries",
            "Runs",
            "Wickets",
            "Dismissals",
            "Overs",
            "Strike Rate",
            "Economy",
            "Latest Note",
        ],
    ]

    for player in report["players"]:
        rows.append(
            [
                player["name"],
                player["team_name"],
                player["primary_role"],
                player["entries"],
                player["runs"],
                player["wickets"],
                player["dismissals"],
                player["overs"],
                player["strike_rate"],
                player["economy"],
                player["latest_note"] or "",
            ]
        )

    return "\n".join(",".join(csv_escape(value) for value in row) for row in rows)


def csv_escape(value):
    text = str(value)
    if any(character in text for character in [",", '"', "\n"]):
        return '"' + text.replace('"', '""') + '"'
    return text


def build_report_html(report):
    player_cards = "".join(
        f"""
        <tr>
          <td>{html_escape(player['name'])}</td>
          <td>{html_escape(player['team_name'])}</td>
          <td>{html_escape(player['primary_role'])}</td>
          <td>{player['entries']}</td>
          <td>{player['runs']}</td>
          <td>{player['wickets']}</td>
          <td>{player['dismissals']}</td>
          <td>{player['overs']}</td>
          <td>{player['strike_rate']}</td>
          <td>{player['economy']}</td>
          <td>{html_escape(player['latest_note'] or '')}</td>
        </tr>
        """
        for player in report["players"]
    )

    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{html_escape(report['academy_name'])} Report</title>
    <style>
      body {{
        font-family: Arial, sans-serif;
        margin: 32px;
        color: #1f2a24;
      }}
      h1, h2 {{
        margin-bottom: 8px;
      }}
      .meta {{
        color: #5a675f;
        margin-bottom: 16px;
      }}
      .summary {{
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
        margin: 24px 0;
      }}
      .summary-card {{
        border: 1px solid #d7ddd8;
        border-radius: 12px;
        padding: 12px;
      }}
      table {{
        width: 100%;
        border-collapse: collapse;
        margin-top: 20px;
      }}
      th, td {{
        border: 1px solid #d7ddd8;
        padding: 10px;
        text-align: left;
        vertical-align: top;
      }}
      th {{
        background: #eef5f1;
      }}
      @media print {{
        body {{
          margin: 16px;
        }}
      }}
    </style>
  </head>
  <body>
    <h1>{html_escape(report['academy_name'])} Report</h1>
    <p class="meta">Period: {html_escape(report['period_label'])}</p>
    <div class="summary">
      <div class="summary-card"><strong>Total Entries</strong><div>{report['total_entries']}</div></div>
      <div class="summary-card"><strong>Total Runs</strong><div>{report['totals']['runs']}</div></div>
      <div class="summary-card"><strong>Total Wickets</strong><div>{report['totals']['wickets']}</div></div>
      <div class="summary-card"><strong>Average Rating</strong><div>{report['totals']['average_rating']}</div></div>
    </div>
    <h2>Player Breakdown</h2>
    <table>
      <thead>
        <tr>
          <th>Player</th>
          <th>Team</th>
          <th>Role</th>
          <th>Entries</th>
          <th>Runs</th>
          <th>Wickets</th>
          <th>Dismissals</th>
          <th>Overs</th>
          <th>Strike Rate</th>
          <th>Economy</th>
          <th>Latest Note</th>
        </tr>
      </thead>
      <tbody>
        {player_cards}
      </tbody>
    </table>
  </body>
</html>
"""


def html_escape(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def validate_player(payload):
    required = ["name", "primary_role", "level"]
    for key in required:
        if not str(payload.get(key, "")).strip():
            raise ValueError(f"{key.replace('_', ' ').title()} is required.")


def validate_performance(payload):
    required = ["player_id", "session_date", "session_type"]
    for key in required:
        if payload.get(key) in (None, ""):
            raise ValueError(f"{key.replace('_', ' ').title()} is required.")

    date.fromisoformat(payload["session_date"])


def ensure_player_exists(player_id, academy_id):
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id FROM players WHERE id = ? AND academy_id = ?",
            (player_id, academy_id),
        ).fetchone()
    if row is None:
        raise LookupError("Player not found.")


def ensure_performance_exists(performance_id, academy_id):
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id FROM performances WHERE id = ? AND academy_id = ?",
            (performance_id, academy_id),
        ).fetchone()
    if row is None:
        raise LookupError("Performance entry not found.")


def ensure_team_exists(team_id, academy_id):
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id FROM teams WHERE id = ? AND academy_id = ?",
            (team_id, academy_id),
        ).fetchone()
    if row is None:
        raise LookupError("Team not found.")


def nullable_team_id(team_id, academy_id):
    if team_id in (None, "", "null"):
        return None
    team_id = int(team_id)
    ensure_team_exists(team_id, academy_id)
    return team_id


def empty_to_none(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def serve_static(start_response, path):
    file_path = BASE_DIR / path.lstrip("/")
    if not file_path.exists() or file_path.is_dir():
        return text_response(start_response, "Not found", "404 Not Found")

    content_type = "text/html; charset=utf-8"
    if file_path.suffix == ".css":
        content_type = "text/css; charset=utf-8"
    elif file_path.suffix == ".js":
        content_type = "application/javascript; charset=utf-8"

    return text_response(start_response, file_path.read_text(encoding="utf-8"), content_type=content_type)


def app(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")
    parsed = urlparse(f"{path}?{environ.get('QUERY_STRING', '')}")
    query = parse_qs(parsed.query)

    try:
        if path == "/" and method == "GET":
            return serve_static(start_response, "/index.html")
        if path == "/dashboard" and method == "GET":
            try:
                current_coach(environ)
                return serve_static(start_response, "/dashboard.html")
            except PermissionError:
                start_response("302 Found", [("Location", "/")])
                return [b""]
        if path in {"/index.html", "/dashboard.html", "/styles.css", "/app.js"} and method == "GET":
            return serve_static(start_response, path)

        if path == "/api/auth/register" and method == "POST":
            result = register_coach(read_json(environ))
            return json_response(
                start_response,
                {"coach": result["coach"]},
                "201 Created",
                cookies=[result["cookie"]],
            )

        if path == "/api/auth/login" and method == "POST":
            result = login_coach(read_json(environ))
            return json_response(
                start_response,
                {"coach": result["coach"]},
                cookies=[result["cookie"]],
            )

        if path == "/api/auth/logout" and method == "POST":
            cookie = logout_coach(environ)
            return no_content_response(start_response, cookies=[cookie])

        if path == "/api/auth/session" and method == "GET":
            coach = current_coach(environ)
            return json_response(
                start_response,
                {
                    "coach": {
                        "id": coach["id"],
                        "academy_id": coach["academy_id"],
                        "name": coach["name"],
                        "email": coach["email"],
                        "role": coach["role"],
                        "academy_name": coach["academy_name"],
                    }
                },
            )

        coach = current_coach(environ)

        if path == "/api/coaches":
            if method == "GET":
                return json_response(start_response, list_coaches(coach))
            if method == "POST":
                return json_response(
                    start_response,
                    create_coach(read_json(environ), coach),
                    "201 Created",
                )

        if path.startswith("/api/coaches/") and method == "PUT":
            coach_id = int(path.rsplit("/", 1)[-1])
            return json_response(
                start_response,
                update_coach_role(coach_id, read_json(environ), coach),
            )

        if path == "/api/teams":
            if method == "GET":
                if coach["role"] == "Head Coach":
                    return json_response(start_response, list_teams(coach))
                return json_response(start_response, list_teams_for_academy(coach))
            if method == "POST":
                return json_response(start_response, create_team(read_json(environ), coach), "201 Created")

        if path.startswith("/api/teams/") and method == "DELETE":
            team_id = int(path.rsplit("/", 1)[-1])
            delete_team(team_id, coach)
            return no_content_response(start_response)

        if path == "/api/players":
            if method == "GET":
                return json_response(start_response, list_players(coach))
            if method == "POST":
                return json_response(start_response, create_player(read_json(environ), coach), "201 Created")

        if path.startswith("/api/players/"):
            player_id = int(path.rsplit("/", 1)[-1])
            if method == "PUT":
                return json_response(start_response, update_player(player_id, read_json(environ), coach))
            if method == "DELETE":
                delete_player(player_id, coach)
                return no_content_response(start_response)

        if path == "/api/performances":
            if method == "GET":
                return json_response(start_response, list_performances(coach))
            if method == "POST":
                return json_response(
                    start_response,
                    create_performance(read_json(environ), coach),
                    "201 Created",
                )

        if path.startswith("/api/performances/"):
            performance_id = int(path.rsplit("/", 1)[-1])
            if method == "PUT":
                return json_response(
                    start_response,
                    update_performance(performance_id, read_json(environ), coach),
                )
            if method == "DELETE":
                delete_performance(performance_id, coach)
                return no_content_response(start_response)

        if path == "/api/reports" and method == "GET":
            months = int(query.get("months", ["1"])[0])
            player_id = query.get("player_id", ["all"])[0]
            team_id = query.get("team_id", ["all"])[0]
            return json_response(start_response, build_report(months, player_id, team_id, coach))

        if path == "/api/reports/export.csv" and method == "GET":
            months = int(query.get("months", ["1"])[0])
            player_id = query.get("player_id", ["all"])[0]
            team_id = query.get("team_id", ["all"])[0]
            report = build_report(months, player_id, team_id, coach)
            return downloadable_response(
                start_response,
                build_report_csv(report),
                "cricket-report.csv",
                "text/csv; charset=utf-8",
            )

        if path == "/api/reports/print" and method == "GET":
            months = int(query.get("months", ["1"])[0])
            player_id = query.get("player_id", ["all"])[0]
            team_id = query.get("team_id", ["all"])[0]
            report = build_report(months, player_id, team_id, coach)
            return text_response(
                start_response,
                build_report_html(report),
                content_type="text/html; charset=utf-8",
            )

        return text_response(start_response, "Not found", "404 Not Found")
    except ValueError as error:
        return json_response(start_response, {"error": str(error)}, "400 Bad Request")
    except LookupError as error:
        return json_response(start_response, {"error": str(error)}, "404 Not Found")
    except PermissionError as error:
        return json_response(start_response, {"error": str(error)}, "401 Unauthorized")
    except sqlite3.IntegrityError:
        return json_response(
            start_response,
            {"error": "This email or academy entry already exists."},
            "409 Conflict",
        )
    except Exception as error:
        return json_response(start_response, {"error": f"Server error: {error}"}, "500 Internal Server Error")


if __name__ == "__main__":
    init_db()
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    server = make_server(host, port, app)
    print(f"Cricket Coach Tracker running on http://{host}:{port}")
    server.serve_forever()
