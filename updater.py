"""
Self-update for the packaged .exe.

Only runs when frozen (a real PyInstaller build) — `python web_app.py` in
dev never touches this. On startup it checks the GitHub repo's latest
release for a newer build than the one baked into this exe; if found, it
downloads the new .exe, swaps it in for the currently-running one, and
relaunches — all before the dashboard opens, so nothing mid-run (like an
active application session) is ever interrupted by an update.

Windows won't let a running process overwrite its own .exe file, but it
will let you rename/delete it out from under itself as long as the handle
stays open — so the swap is done by a tiny detached helper script that
waits for this process to actually exit, then does the rename and
relaunch.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

REPO = "Vansh9115/naukri-auto-applier-pro"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases/latest"
REQUEST_TIMEOUT = 8


def get_local_version(bundle_dir):
    try:
        with open(os.path.join(bundle_dir, "version.txt"), "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return 0


def _fetch_latest_release():
    req = urllib.request.Request(RELEASES_API, headers={"User-Agent": "NaukriAutoApplierPro-Updater"})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as r:
        return json.load(r)


def _parse_version(tag_name):
    # Tags look like "build-42" (see .github/workflows/build-release.yml).
    digits = "".join(ch for ch in tag_name if ch.isdigit())
    return int(digits) if digits else 0


def _spawn_swap_and_relaunch(pid, exe_path, new_path):
    """Write and launch a detached helper that waits for `pid` to exit,
    then replaces exe_path with new_path and starts it again."""
    helper_path = exe_path + ".updater.bat"
    script = f"""@echo off
:wait
tasklist /fi "PID eq {pid}" | find "{pid}" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait
)
timeout /t 1 /nobreak >nul
del /f /q "{exe_path}"
move /y "{new_path}" "{exe_path}"
start "" "{exe_path}"
del /f /q "%~f0"
"""
    with open(helper_path, "w", encoding="utf-8") as f:
        f.write(script)
    subprocess.Popen(
        ["cmd", "/c", helper_path],
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
        close_fds=True,
    )


def check_and_apply_update(bundle_dir, log=print):
    """Returns True if an update was found and this process is about to
    exit to let it apply (caller should stop startup immediately)."""
    if not getattr(sys, "frozen", False):
        return False  # dev runs (`python web_app.py`) are never auto-updated

    local_version = get_local_version(bundle_dir)
    try:
        release = _fetch_latest_release()
    except Exception as e:
        log(f"Update check skipped ({e}).")
        return False

    remote_version = _parse_version(release.get("tag_name", ""))
    if remote_version <= local_version:
        log(f"Up to date (build {local_version}).")
        return False

    asset = next(
        (a for a in release.get("assets", []) if a.get("name", "").lower().endswith(".exe")),
        None,
    )
    if not asset:
        log("Update found but no .exe asset attached to the release — skipping.")
        return False

    log(f"⬆️ Update found: build {local_version} -> build {remote_version}. Downloading...")
    exe_path = sys.executable
    new_path = exe_path + ".new"
    try:
        urllib.request.urlretrieve(asset["browser_download_url"], new_path)
    except Exception as e:
        log(f"Update download failed ({e}); continuing on current version.")
        try:
            os.remove(new_path)
        except OSError:
            pass
        return False

    # Sanity-check the download isn't a truncated/corrupt partial file
    # before we commit to replacing the working exe with it.
    if os.path.getsize(new_path) < 5_000_000:
        log("Downloaded update looked too small/corrupt — skipping.")
        try:
            os.remove(new_path)
        except OSError:
            pass
        return False

    log("Update downloaded. Restarting...")
    _spawn_swap_and_relaunch(os.getpid(), exe_path, new_path)
    return True
