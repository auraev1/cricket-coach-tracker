const authShell = document.getElementById("authShell");
const appShell = document.getElementById("appShell");
const authTabs = document.querySelectorAll("[data-auth-tab]");
const authForms = document.querySelectorAll("[data-auth-form]");
const loginForm = document.getElementById("loginForm");
const registerForm = document.getElementById("registerForm");
const logoutButton = document.getElementById("logoutButton");
const coachForm = document.getElementById("coachForm");
const teamForm = document.getElementById("teamForm");
const playerForm = document.getElementById("playerForm");
const performanceForm = document.getElementById("performanceForm");
const coachList = document.getElementById("coachList");
const playerList = document.getElementById("playerList");
const performanceList = document.getElementById("performanceList");
const teamList = document.getElementById("teamList");
const performancePlayer = document.getElementById("performancePlayer");
const playerTeam = document.getElementById("playerTeam");
const reportPlayer = document.getElementById("reportPlayer");
const reportTeam = document.getElementById("reportTeam");
const reportRange = document.getElementById("reportRange");
const reportOutput = document.getElementById("reportOutput");
const exportCsvButton = document.getElementById("exportCsv");
const printReportButton = document.getElementById("printReport");
const playerCount = document.getElementById("playerCount");
const entryCount = document.getElementById("entryCount");
const teamCount = document.getElementById("teamCount");
const statusBanner = document.getElementById("statusBanner");
const academyName = document.getElementById("academyName");
const coachName = document.getElementById("coachName");
const coachRole = document.getElementById("coachRole");
const coachManagementPanel = document.getElementById("coachManagementPanel");
const teamPanelCopy = document.getElementById("teamPanelCopy");

const state = {
  coach: null,
  coaches: [],
  teams: [],
  players: [],
  performances: [],
  editingPlayerId: null,
  editingPerformanceId: null,
};

if (document.getElementById("performanceDate")) {
  document.getElementById("performanceDate").valueAsDate = new Date();
}

if (authShell) {
  authTabs.forEach((button) => {
    button.addEventListener("click", () => switchAuthTab(button.dataset.authTab));
  });

  loginForm.addEventListener("submit", handleLogin);
  registerForm.addEventListener("submit", handleRegister);
}

if (appShell) {
  logoutButton.addEventListener("click", handleLogout);
  coachForm.addEventListener("submit", handleCoachSubmit);
  teamForm.addEventListener("submit", handleTeamSubmit);
  playerForm.addEventListener("submit", handlePlayerSubmit);
  performanceForm.addEventListener("submit", handlePerformanceSubmit);
  document.getElementById("generateReport").addEventListener("click", renderReport);
  exportCsvButton.addEventListener("click", exportCsv);
  printReportButton.addEventListener("click", printReport);
  reportPlayer.addEventListener("change", renderReport);
  reportTeam.addEventListener("change", renderReport);
  reportRange.addEventListener("change", renderReport);
  document.getElementById("cancelPlayerEdit").addEventListener("click", resetPlayerForm);
  document
    .getElementById("cancelPerformanceEdit")
    .addEventListener("click", resetPerformanceForm);
}

bootstrap();

async function bootstrap() {
  if (authShell) {
    switchAuthTab("login");

    try {
      await request("/api/auth/session");
      window.location.href = "/dashboard";
    } catch (error) {
      showAuth();
    }
    return;
  }

  if (appShell) {
    try {
      const session = await request("/api/auth/session");
      state.coach = session.coach;
      await loadDashboard();
    } catch (error) {
      window.location.href = "/";
    }
  }
}

function switchAuthTab(tab) {
  authTabs.forEach((button) => {
    button.classList.toggle("tab-active", button.dataset.authTab === tab);
  });

  authForms.forEach((form) => {
    form.hidden = form.dataset.authForm !== tab;
  });
}

function showAuth() {
  if (authShell) {
    authShell.hidden = false;
  }
}

function showApp() {
  if (appShell) {
    appShell.hidden = false;
  }
}

async function handleRegister(event) {
  event.preventDefault();

  const payload = {
    coach_name: document.getElementById("registerCoachName").value.trim(),
    academy_name: document.getElementById("registerAcademyName").value.trim(),
    email: document.getElementById("registerEmail").value.trim(),
    password: document.getElementById("registerPassword").value,
    role: document.getElementById("registerRole").value,
  };

  try {
    const response = await request("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.coach = response.coach;
    registerForm.reset();
    window.location.href = "/dashboard";
  } catch (error) {
    showStatus(error.message, true);
  }
}

async function handleLogin(event) {
  event.preventDefault();

  const payload = {
    email: document.getElementById("loginEmail").value.trim(),
    password: document.getElementById("loginPassword").value,
  };

  try {
    const response = await request("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.coach = response.coach;
    loginForm.reset();
    window.location.href = "/dashboard";
  } catch (error) {
    showStatus(error.message, true);
  }
}

async function handleLogout() {
  try {
    await request("/api/auth/logout", { method: "POST" });
  } finally {
    state.coach = null;
    state.teams = [];
    state.coaches = [];
    state.players = [];
    state.performances = [];
    if (playerForm) {
      resetPlayerForm();
    }
    if (performanceForm) {
      resetPerformanceForm();
    }
    window.location.href = "/";
  }
}

async function loadDashboard() {
  const loaders = [loadTeams(), loadPlayers(), loadPerformances()];
  if (isHeadCoach()) {
    loaders.push(loadCoaches());
  } else {
    state.coaches = [];
    renderCoachList();
  }
  await Promise.all(loaders);
  academyName.textContent = state.coach.academy_name;
  coachName.textContent = state.coach.name;
  coachRole.textContent = `(${state.coach.role})`;
  coachManagementPanel.hidden = !isHeadCoach();
  teamPanelCopy.textContent = isHeadCoach()
    ? "Create academy teams and age groups."
    : "View academy teams managed by the head coach.";
  teamForm.hidden = !isHeadCoach();
  showApp();
  await renderReport();
}

async function loadCoaches() {
  state.coaches = await request("/api/coaches");
  renderCoachList();
}

async function loadTeams() {
  state.teams = await request("/api/teams");
  renderTeamOptions();
  renderTeamList();
  teamCount.textContent = state.teams.length;
}

async function loadPlayers() {
  state.players = await request("/api/players");
  renderPlayerOptions();
  renderPlayerList();
  renderPerformanceList();
  playerCount.textContent = state.players.length;
}

async function loadPerformances() {
  state.performances = await request("/api/performances");
  renderPerformanceList();
  entryCount.textContent = state.performances.length;
}

async function handleTeamSubmit(event) {
  event.preventDefault();

  const payload = {
    name: document.getElementById("teamName").value.trim(),
    age_group: document.getElementById("teamAgeGroup").value.trim(),
  };

  try {
    await request("/api/teams", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    teamForm.reset();
    showStatus("Team added.");
    await Promise.all([loadTeams(), loadPlayers(), renderReport()]);
  } catch (error) {
    showStatus(error.message, true);
  }
}

async function handleCoachSubmit(event) {
  event.preventDefault();

  const payload = {
    name: document.getElementById("newCoachName").value.trim(),
    email: document.getElementById("newCoachEmail").value.trim(),
    password: document.getElementById("newCoachPassword").value,
    role: document.getElementById("newCoachRole").value,
  };

  try {
    if (payload.role === "Head Coach") {
      await request("/api/coaches", {
        method: "POST",
        body: JSON.stringify({ ...payload, role: "Assistant Coach" }),
      });
      await loadCoaches();
      const created = state.coaches.find((coach) => coach.email === payload.email);
      if (created) {
        await request(`/api/coaches/${created.id}`, {
          method: "PUT",
          body: JSON.stringify({ role: "Head Coach" }),
        });
      }
      showStatus("Head coach reassigned.");
    } else {
      await request("/api/coaches", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      showStatus("Coach added.");
    }

    coachForm.reset();
    document.getElementById("newCoachRole").value = "Assistant Coach";
    await loadCoaches();
  } catch (error) {
    showStatus(error.message, true);
  }
}

async function handlePlayerSubmit(event) {
  event.preventDefault();

  const payload = {
    team_id: playerTeam.value || null,
    name: document.getElementById("playerName").value.trim(),
    age: nullableNumber(document.getElementById("playerAge").value),
    primary_role: document.getElementById("primaryRole").value,
    level: document.getElementById("playerLevel").value,
    bowling_style: document.getElementById("bowlingStyle").value.trim(),
    bowling_arm: document.getElementById("bowlingArm").value.trim(),
    batting_hand: document.getElementById("battingHand").value.trim(),
    batting_position: document.getElementById("battingPosition").value.trim(),
    batting_style: document.getElementById("battingStyle").value.trim(),
    secondary_skill: document.getElementById("secondarySkill").value.trim(),
    notes: document.getElementById("playerNotes").value.trim(),
  };

  try {
    if (state.editingPlayerId) {
      await request(`/api/players/${state.editingPlayerId}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      showStatus("Player updated.");
    } else {
      await request("/api/players", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      showStatus("Player added.");
    }

    resetPlayerForm();
    await Promise.all([loadPlayers(), loadPerformances(), renderReport()]);
  } catch (error) {
    showStatus(error.message, true);
  }
}

async function handlePerformanceSubmit(event) {
  event.preventDefault();

  const payload = {
    player_id: Number(performancePlayer.value),
    session_date: document.getElementById("performanceDate").value,
    session_type: document.getElementById("sessionType").value,
    runs: numberValue("runs"),
    balls_faced: numberValue("ballsFaced"),
    wickets: numberValue("wickets"),
    overs: floatValue("overs"),
    runs_conceded: numberValue("runsConceded"),
    dismissals: numberValue("dismissals"),
    coach_rating: numberValue("coachRating"),
    notes: document.getElementById("performanceNotes").value.trim(),
  };

  try {
    if (state.editingPerformanceId) {
      await request(`/api/performances/${state.editingPerformanceId}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      showStatus("Performance updated.");
    } else {
      await request("/api/performances", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      showStatus("Performance logged.");
    }

    resetPerformanceForm();
    await Promise.all([loadPerformances(), renderReport()]);
  } catch (error) {
    showStatus(error.message, true);
  }
}

function renderTeamOptions() {
  const currentTeamValue = playerTeam.value;
  const currentReportTeam = reportTeam.value;
  const options = state.teams
    .map((team) => `<option value="${team.id}">${escapeHtml(team.name)}</option>`)
    .join("");

  playerTeam.innerHTML = `<option value="">No team yet</option>${options}`;
  reportTeam.innerHTML = `<option value="all">All teams</option>${options}`;

  if (currentTeamValue) {
    playerTeam.value = currentTeamValue;
  }

  if (currentReportTeam) {
    reportTeam.value = currentReportTeam;
  }
}

function renderPlayerOptions() {
  const currentPerformanceValue = performancePlayer.value;
  const currentReportValue = reportPlayer.value;
  const options = state.players
    .map((player) => `<option value="${player.id}">${escapeHtml(player.name)}</option>`)
    .join("");

  performancePlayer.innerHTML = `<option value="">Select player</option>${options}`;
  reportPlayer.innerHTML = `<option value="all">All players</option>${options}`;

  if (currentPerformanceValue) {
    performancePlayer.value = currentPerformanceValue;
  }

  if (currentReportValue) {
    reportPlayer.value = currentReportValue;
  }
}

function renderTeamList() {
  if (!state.teams.length) {
    teamList.innerHTML = `<p class="empty-state">No teams created yet.</p>`;
    return;
  }

  teamList.innerHTML = state.teams
    .map(
      (team) => `
        <article class="mini-card">
          <div>
            <h4>${escapeHtml(team.name)}</h4>
            <p class="meta">${escapeHtml(team.age_group || "Age group not set")}</p>
          </div>
          ${
            isHeadCoach()
              ? `<button class="ghost-btn danger-btn" type="button" data-action="delete-team" data-id="${team.id}">Delete</button>`
              : ""
          }
        </article>
      `
    )
    .join("");

  bindDynamicActions();
}

function renderCoachList() {
  if (!isHeadCoach()) {
    coachList.innerHTML = `<p class="empty-state">Only the head coach can manage coach roles.</p>`;
    return;
  }

  if (!state.coaches.length) {
    coachList.innerHTML = `<p class="empty-state">No coaches added yet.</p>`;
    return;
  }

  coachList.innerHTML = state.coaches
    .map(
      (coach) => `
        <article class="mini-card">
          <div>
            <h4>${escapeHtml(coach.name)}</h4>
            <p class="meta">${escapeHtml(coach.email)} • ${escapeHtml(coach.role)}</p>
          </div>
          ${
            coach.role === "Assistant Coach"
              ? `<button class="ghost-btn" type="button" data-action="promote-coach" data-id="${coach.id}">Make Head Coach</button>`
              : ""
          }
        </article>
      `
    )
    .join("");

  bindDynamicActions();
}

function renderPlayerList() {
  if (!state.players.length) {
    playerList.innerHTML = `<p class="empty-state">No players added yet.</p>`;
    return;
  }

  playerList.innerHTML = state.players
    .map((player) => {
      const labels = [
        player.team_name,
        player.primary_role,
        player.level,
        player.bowling_style,
        player.bowling_arm,
        player.batting_hand,
        player.batting_position,
        player.batting_style,
        player.secondary_skill,
      ].filter(Boolean);

      return `
        <article class="player-card">
          <div class="player-card-header">
            <div>
              <h3>${escapeHtml(player.name)}</h3>
              <p class="meta">
                ${player.age ? `${player.age} years` : "Age not set"} • ${escapeHtml(player.primary_role)}
              </p>
            </div>
            <div class="action-row">
              <button class="ghost-btn" type="button" data-action="edit-player" data-id="${player.id}">Edit</button>
              <button class="ghost-btn danger-btn" type="button" data-action="delete-player" data-id="${player.id}">Delete</button>
            </div>
          </div>
          <div class="badge-row">
            ${labels.map((label) => `<span class="badge">${escapeHtml(label)}</span>`).join("")}
          </div>
          <p class="meta">${escapeHtml(player.notes || "No coach notes yet.")}</p>
        </article>
      `;
    })
    .join("");

  bindDynamicActions();
}

function renderPerformanceList() {
  if (!state.performances.length) {
    performanceList.innerHTML =
      `<p class="empty-state">No performance entries added yet.</p>`;
    return;
  }

  performanceList.innerHTML = state.performances
    .map((entry) => `
      <article class="entry-card">
        <div class="player-card-header">
          <div>
            <h4>${escapeHtml(entry.player_name || "Unknown Player")}</h4>
            <p class="meta">${escapeHtml(entry.session_type)} • ${formatDate(entry.session_date)}</p>
          </div>
          <div class="action-row">
            <button class="ghost-btn" type="button" data-action="edit-performance" data-id="${entry.id}">Edit</button>
            <button class="ghost-btn danger-btn" type="button" data-action="delete-performance" data-id="${entry.id}">Delete</button>
          </div>
        </div>
        <div class="entry-grid">
          <div><small>Runs</small><span>${entry.runs}</span></div>
          <div><small>Wickets</small><span>${entry.wickets}</span></div>
          <div><small>Dismissals</small><span>${entry.dismissals}</span></div>
          <div><small>Overs</small><span>${entry.overs.toFixed(1)}</span></div>
          <div><small>Conceded</small><span>${entry.runs_conceded}</span></div>
          <div><small>Rating</small><span>${entry.coach_rating}/10</span></div>
        </div>
        <p class="meta">${escapeHtml(entry.notes || "No session notes.")}</p>
      </article>
    `)
    .join("");

  bindDynamicActions();
}

async function renderReport() {
  try {
    const params = currentReportParams();
    const report = await request(
      `/api/reports?${params.toString()}`
    );

    if (!report.total_entries) {
      reportOutput.innerHTML = `
        <p class="empty-state">No performance entries found for the selected report range.</p>
      `;
      return;
    }

    reportOutput.innerHTML = `
      <section class="summary-card">
        <div class="report-summary">
          <div>
            <h3>${escapeHtml(report.academy_name)} Report</h3>
            <p class="meta">Review period: ${escapeHtml(report.period_label)}</p>
          </div>
          <div class="summary-chip">${report.total_entries} entries</div>
        </div>
        <div class="summary-grid">
          <div><small>Total Runs</small><strong>${report.totals.runs}</strong></div>
          <div><small>Total Wickets</small><strong>${report.totals.wickets}</strong></div>
          <div><small>Dismissals</small><strong>${report.totals.dismissals}</strong></div>
          <div><small>Average Rating</small><strong>${report.totals.average_rating}</strong></div>
        </div>
      </section>
      ${report.players
        .map(
          (player) => `
            <article class="entry-card">
              <h4>${escapeHtml(player.name)}</h4>
              <p class="meta">${escapeHtml(player.team_name)} • ${escapeHtml(player.primary_role)} • ${player.entries} log(s)</p>
              <div class="entry-grid">
                <div><small>Runs</small><span>${player.runs}</span></div>
                <div><small>Wickets</small><span>${player.wickets}</span></div>
                <div><small>Dismissals</small><span>${player.dismissals}</span></div>
                <div><small>Overs</small><span>${player.overs}</span></div>
                <div><small>Strike Rate</small><span>${player.strike_rate}</span></div>
                <div><small>Economy</small><span>${player.economy}</span></div>
              </div>
              <p class="meta">Latest note: ${escapeHtml(player.latest_note || "No notes available for this period.")}</p>
            </article>
          `
        )
        .join("")}
    `;
  } catch (error) {
    showStatus(error.message, true);
  }
}

function exportCsv() {
  const params = currentReportParams();
  window.location.href = `/api/reports/export.csv?${params.toString()}`;
}

function printReport() {
  const params = currentReportParams();
  window.open(`/api/reports/print?${params.toString()}`, "_blank", "noopener");
}

function bindDynamicActions() {
  document.querySelectorAll("[data-action]").forEach((button) => {
    button.onclick = async () => {
      const { action, id } = button.dataset;

      try {
        if (action === "delete-team") {
          await request(`/api/teams/${id}`, { method: "DELETE" });
          showStatus("Team deleted.");
          await Promise.all([loadTeams(), loadPlayers(), renderReport()]);
          return;
        }

        if (action === "promote-coach") {
          await request(`/api/coaches/${id}`, {
            method: "PUT",
            body: JSON.stringify({ role: "Head Coach" }),
          });
          showStatus("Head coach updated.");
          const session = await request("/api/auth/session");
          state.coach = session.coach;
          await loadDashboard();
          return;
        }

        if (action === "edit-player") {
          startPlayerEdit(Number(id));
          return;
        }

        if (action === "delete-player") {
          await request(`/api/players/${id}`, { method: "DELETE" });
          if (state.editingPlayerId === Number(id)) {
            resetPlayerForm();
          }
          showStatus("Player deleted.");
          await Promise.all([loadPlayers(), loadPerformances(), renderReport()]);
          return;
        }

        if (action === "edit-performance") {
          startPerformanceEdit(Number(id));
          return;
        }

        if (action === "delete-performance") {
          await request(`/api/performances/${id}`, { method: "DELETE" });
          if (state.editingPerformanceId === Number(id)) {
            resetPerformanceForm();
          }
          showStatus("Performance deleted.");
          await Promise.all([loadPerformances(), renderReport()]);
        }
      } catch (error) {
        showStatus(error.message, true);
      }
    };
  });
}

function startPlayerEdit(playerId) {
  const player = state.players.find((item) => item.id === playerId);
  if (!player) {
    return;
  }

  state.editingPlayerId = playerId;
  playerTeam.value = player.team_id || "";
  document.getElementById("playerName").value = player.name || "";
  document.getElementById("playerAge").value = player.age || "";
  document.getElementById("primaryRole").value = player.primary_role || "";
  document.getElementById("playerLevel").value = player.level || "";
  document.getElementById("bowlingStyle").value = player.bowling_style || "";
  document.getElementById("bowlingArm").value = player.bowling_arm || "";
  document.getElementById("battingHand").value = player.batting_hand || "";
  document.getElementById("battingPosition").value = player.batting_position || "";
  document.getElementById("battingStyle").value = player.batting_style || "";
  document.getElementById("secondarySkill").value = player.secondary_skill || "";
  document.getElementById("playerNotes").value = player.notes || "";
  document.getElementById("playerSubmitText").textContent = "Update Player";
  document.getElementById("cancelPlayerEdit").hidden = false;
}

function startPerformanceEdit(performanceId) {
  const entry = state.performances.find((item) => item.id === performanceId);
  if (!entry) {
    return;
  }

  state.editingPerformanceId = performanceId;
  performancePlayer.value = String(entry.player_id);
  document.getElementById("performanceDate").value = entry.session_date;
  document.getElementById("sessionType").value = entry.session_type || "";
  document.getElementById("runs").value = entry.runs;
  document.getElementById("ballsFaced").value = entry.balls_faced;
  document.getElementById("wickets").value = entry.wickets;
  document.getElementById("overs").value = entry.overs;
  document.getElementById("runsConceded").value = entry.runs_conceded;
  document.getElementById("dismissals").value = entry.dismissals;
  document.getElementById("coachRating").value = entry.coach_rating;
  document.getElementById("performanceNotes").value = entry.notes || "";
  document.getElementById("performanceSubmitText").textContent = "Update Performance";
  document.getElementById("cancelPerformanceEdit").hidden = false;
}

function resetPlayerForm() {
  state.editingPlayerId = null;
  playerForm.reset();
  playerTeam.value = "";
  document.getElementById("playerSubmitText").textContent = "Save Player";
  document.getElementById("cancelPlayerEdit").hidden = true;
}

function resetPerformanceForm() {
  state.editingPerformanceId = null;
  performanceForm.reset();
  document.getElementById("performanceDate").valueAsDate = new Date();
  document.getElementById("coachRating").value = 7;
  document.getElementById("performanceSubmitText").textContent = "Add Performance";
  document.getElementById("cancelPerformanceEdit").hidden = true;
}

async function request(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: "Request failed." }));
    throw new Error(error.error || "Request failed.");
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

function showStatus(message, isError = false) {
  statusBanner.textContent = message;
  statusBanner.hidden = false;
  statusBanner.classList.toggle("error-banner", isError);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function numberValue(id) {
  return Number(document.getElementById(id).value || 0);
}

function floatValue(id) {
  return parseFloat(document.getElementById(id).value || "0");
}

function nullableNumber(value) {
  if (value === "") {
    return null;
  }

  return Number(value);
}

function formatDate(value) {
  const date = new Date(`${value}T00:00:00`);
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function currentReportParams() {
  const params = new URLSearchParams();
  params.set("months", String(Number(reportRange.value)));
  params.set("player_id", reportPlayer.value || "all");
  params.set("team_id", reportTeam.value || "all");
  return params;
}

function isHeadCoach() {
  return state.coach?.role === "Head Coach";
}
