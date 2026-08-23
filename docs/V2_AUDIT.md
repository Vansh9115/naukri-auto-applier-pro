# V2 Audit

## Architecture (actual, as of 2026-08-23)
- **Single-user local tool**, not a SaaS app. No backend framework beyond a thin Flask server.
- `web_app.py` — Flask app (port 5000) serving `index.html`; routes: `/api/config`, `/api/upload-resume`, `/api/start`, `/api/stop`, `/api/google-login`, `/api/manual-login`, `/api/status`, `/api/report`. All wired correctly to real handlers — no dead buttons found in `index.html`.
- `app.py` — parallel desktop GUI (CustomTkinter/Tkinter) duplicating the web UI, plus a "Sync & Push to GitHub" feature that force-pushes to a hardcoded repo using a PAT stored in `config.json`.
- `naukri_bot.py` — Playwright automation (`NaukriBot` class) driving real installed Chrome via `launch_persistent_context`. **Naukri only — no LinkedIn integration exists anywhere in the repo**, despite the task brief assuming LinkedIn+Naukri.
- `tracker.py` — CSV-based tracking (`applied_jobs.csv`), not a database. Columns: timestamp, job_id, title, company, location, url, status, notes.
- `config.json` — single flat profile (credentials, keywords, locations, CTC, notice period, resume path). Doubles as the "candidate profile."
- No web OAuth (Google "login" = opening a real Chrome window and letting the user click Naukri's own Google button — session persists via Chrome profile, not tokens Claude/the app ever sees).
- No email integration, no AI/LLM calls, no job-matching/scoring, no resume tailoring, no dashboard, no diagnostics page, no DB, **no tests**.

## Startup check
- `py -3 -m py_compile` on all four modules: **OK**, no syntax errors.
- Dependencies (flask, playwright, customtkinter, dulwich, pandas, rich) all importable in the active Python 3.14 env.
- `requirements.txt` is missing `customtkinter` and `dulwich` (used only by `app.py`, undeclared).

## Working
- Web UI ↔ Flask routes ↔ `NaukriBot`/`JobTracker` wiring is intact (start/stop/status/login/upload/report).
- CSV-based duplicate check (`JobTracker.is_applied`) by job_id, url, or title+company signature.
- Basic status taxonomy already exists: `APPLIED`, `APPLIED_UNVERIFIED`, `ALREADY_APPLIED`, `EXTERNAL`, `FAILED`, `SKIPPED`.
- HTML analytics report generation.

## Broken / root causes
1. **`requirements.txt` incomplete** — fresh installs following the README would fail on `app.py` (missing `customtkinter`, `dulwich`). Root cause: dependency added ad hoc, never synced to requirements.
2. **No structured skip/failure reasons** — `notes` is a free-text dump (e.g. raw exception text, `"No Apply button"`); no `reason_code` taxonomy, no way to filter/report by cause. Root cause: tracker schema was never extended past MVP.
3. **Selectors are broad/fragile** (`div[class*='drawer']`, generic text-match chains) with blind `time.sleep`-based waits and no retry/fallback strategy — Naukri DOM changes will silently increase skip/failure rates. Root cause: single-pass selector lists, no verification step after actions.
4. **No CAPTCHA/challenge detection** — an auth challenge would fall through to the generic timeout/failure path rather than a clear `AUTH_REQUIRED`/`MANUAL_REVIEW` signal.
5. **`config.json` stores the Naukri password and a GitHub PAT in plaintext** in a file that isn't gitignored by name (only broad patterns) — real risk if the repo is ever pushed with it populated. Currently empty, but the mechanism itself is unsafe.
6. **No automated tests** at all — no regression safety net for matching/tracking/parsing logic.
7. **Scope gap vs. this task's brief**: the brief specifies a multi-platform (LinkedIn+Naukri) SaaS product — OAuth login, a database, AI question-answering, resume tailoring, a multi-page dashboard, job-match scoring. None of that exists today; the real app is a single-profile Naukri desktop/local-web automation script backed by a CSV file.

## Recommended fixes (incremental, keeps existing app intact)
- Fix `requirements.txt`; keep `python -m py_compile` as a cheap CI-less smoke test.
- Extend `tracker.py`'s CSV schema with `reason_code`, `match_score`, `attempt_count`, `resume_version` columns (backward compatible — new columns, old rows still parse) instead of introducing a full DB, unless the user wants to invest in that.
- Add a `reason_code` enum in `naukri_bot.py` and populate it at each skip/fail site instead of raw notes.
- Wrap Playwright interactions in `safe_click`/`wait_for_visible`/retry-with-fallback-selector helpers; add a screenshot-on-unexpected-failure hook.
- Detect CAPTCHA/security-challenge markers and route to `AUTH_REQUIRED`/`MANUAL_REVIEW` instead of generic `FAILED`.
- Add a `.gitignore` rule for `config.json` (keep `config.json.example`), and stop echoing the password back into the UI form.
- Add `pytest` + a few focused unit tests (tracker duplicate logic, `SmartAnswerEngine.answer`/`should_select`, config load).

The remaining brief items (OAuth backend, database, multi-platform LinkedIn support, AI resume tailoring, full SaaS dashboard) would require building substantially new subsystems, not repairing existing ones — flagging this for a scoping decision before building it, per "preserve working functionality, don't rewrite from scratch" guidance.
