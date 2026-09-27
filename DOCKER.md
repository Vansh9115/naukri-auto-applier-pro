# Running via Docker (WSL2)

Everything the app needs — Python, Playwright, real Chrome, all system
libraries — is baked into the image. The only things you install on the
host are WSL2 and Docker Desktop, both free.

**Before you commit to this path, know the trade-off:** because the bot
always opens a *visible* browser window (not headless — that's deliberate,
so Google's login doesn't flag it as a bot), and a container has no
display of its own, logging in means opening a *second* browser tab
(a VNC viewer) alongside the dashboard. For a non-technical friend, that's
a more moving parts than the standalone `.exe` (see `SHARE_WITH_FRIEND.md`)
— this route is worth it when you specifically want to avoid antivirus/
SmartScreen friction on the `.exe`, or want to run it on Linux/Mac, not
because it's simpler to hand to someone.

## One-time setup

### 1. Install WSL2 (Windows only — skip on Linux/Mac)
In an **administrator** PowerShell:
```powershell
wsl --install
```
This requires a restart. Full details: https://aka.ms/wslinstall

### 2. Install Docker Desktop
Download from [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) and install it — on Windows it auto-detects and uses the WSL2 backend. Free for individual/personal use (and for small businesses/most cases — Docker's paid tier is for large companies; check their current terms if in doubt).

### 3. Get the code
```bash
git clone https://github.com/Vansh9115/naukri-auto-applier-pro.git
cd naukri-auto-applier-pro
```

## Running it

```bash
./docker-start.sh
```
(First run builds the image — a few minutes. After that, `docker compose up` starts in seconds.)

Then open two tabs:
- **`http://localhost:5000`** — the dashboard: set keywords/CTC/resume, click Start.
- **`http://localhost:6080/vnc.html`** — click **Connect** (no password) to see the actual containerized Chrome window. You only need this tab for the one-time Google login, or if you ever want to watch it work / solve a CAPTCHA — the rest of the time the dashboard alone is enough.

Everything the container writes (`config.json`, `applied_jobs.csv`, the Chrome login session, uploaded resumes) lands in `./docker-data/` on your machine, so it survives `docker compose down` and rebuilds.

## Stopping it
```bash
docker compose down
```

## Keeping it updated

Every push to `main` also publishes a fresh image to
`ghcr.io/vansh9115/naukri-auto-applier-pro:latest` (see
`.github/workflows/docker-build.yml`).

**One-time setup after the first push:** GitHub Container Registry
packages default to **private** even in a public repo, which would block
anyone else from pulling anonymously. After the workflow runs once, go to
the package's page (linked from the repo sidebar under "Packages") →
**Package settings** → **Change visibility** → **Public**.

To pick up a new version:
```bash
docker compose pull && docker compose up -d
```

To make that automatic (so a running container updates itself the way the
`.exe` does), run [Watchtower](https://containrrr.dev/watchtower/) — a
free, widely-used tool that watches your running containers and restarts
them when a newer image is published:
```bash
docker run -d --name watchtower -v /var/run/docker.sock:/var/run/docker.sock \
    containrrr/watchtower --interval 3600
```
That's a one-time setup step, separate from this app — it'll then keep
*any* container it finds current, checking hourly.
