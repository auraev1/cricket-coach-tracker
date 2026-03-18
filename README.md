# Cricket Coach Tracker

A lightweight full-stack cricket coaching app built with Python, SQLite, HTML, CSS, and vanilla JavaScript.

## What it does

- Creates coach accounts with login sessions
- Supports `Head Coach` and `Assistant Coach` roles
- Organizes data by academy and team
- Stores detailed player profiles in SQLite
- Tracks batting, bowling, wicketkeeping, and all-rounder attributes
- Records match or training performance entries
- Supports editing and deleting teams, players, and performance logs
- Generates monthly, 3-month, 6-month, and yearly reports from backend data

## Run locally

1. From the project folder, start the server:

```bash
python3 server.py
```

2. Open [http://127.0.0.1:8000](http://127.0.0.1:8000)

## Put it online

The quickest option is to deploy it as a web app on Render.

1. Put this project in a GitHub repository
2. Create a Render account
3. In Render, choose `New +` -> `Web Service`
4. Connect your GitHub repo
5. Render will detect [`render.yaml`](./render.yaml)
6. Deploy the service
7. Open the public URL Render gives you on your iPhone

Important:

- This app currently uses SQLite
- For real production use, choose a Render plan with persistent disk or move later to PostgreSQL
- Without persistent storage, your data can be lost on redeploy or restart

## iPhone use

Once deployed online:

1. Open the app URL in Safari on iPhone
2. Tap `Share`
3. Tap `Add to Home Screen`
4. Open it from your home screen like an app

## Files

- `server.py`: Python backend and SQLite API
- `index.html`: frontend markup
- `styles.css`: UI styling
- `app.js`: frontend behavior and API integration
- `cricket_coach.db`: SQLite database created on first run

## Suggested next upgrades

- role-based access for head coach vs assistant coach
- Excel or PDF export for reports
- charts for player improvement trends
- attendance and fitness tracking
- bowling and batting drill history

## Report export

- Use `Export CSV` to download an Excel-friendly report for the current filters
- Use `Print / Save PDF` to open a print-ready report that can be saved as PDF from the browser

## Role access

- The first coach created in an academy becomes the `Head Coach`
- Only the `Head Coach` can add teams, add coaches, or promote another coach to `Head Coach`
- `Assistant Coach` users can still manage players, performance entries, and reports
