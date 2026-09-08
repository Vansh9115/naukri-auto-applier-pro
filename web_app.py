import os
import sys
import json
import threading
import webbrowser

# Windows consoles often default to cp1252, which can't encode the emoji
# used in log/status output below; force UTF-8 so startup doesn't crash.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# When frozen into a standalone .exe (PyInstaller), bundled read-only files
# (index.html, etc.) live under sys._MEIPASS, a temp dir that's wiped after
# the process exits — never a place to write user data. Everything the app
# writes (config.json, uploads/, applied_jobs.csv, the Chrome profile) must
# live next to the .exe itself so it persists across runs. Both existing
# relative-path code throughout this app and naukri_bot.py/tracker.py assume
# the working directory is the app's home, so chdir there up front.
FROZEN = getattr(sys, "frozen", False)
BUNDLE_DIR = sys._MEIPASS if FROZEN else os.path.dirname(os.path.abspath(__file__))
if FROZEN:
    os.chdir(os.path.dirname(sys.executable))

from flask import Flask, jsonify, request, send_file, render_template_string
from werkzeug.utils import secure_filename
from naukri_bot import NaukriBot, load_config
from tracker import JobTracker

app = Flask(__name__, static_folder=BUNDLE_DIR)
app.config["UPLOAD_FOLDER"] = os.path.abspath("./uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

bot_instance = None
bot_thread = None
login_thread = None
start_lock = threading.Lock()
log_buffer = []


def append_log(msg, level="INFO"):
    icons = {"INFO": "ℹ️", "SUCCESS": "✅", "WARNING": "⚠️", "ERROR": "❌"}
    # Many messages from naukri_bot.py already carry their own leading emoji
    # (e.g. "🚀 Starting..."); only add the level icon when they don't, to
    # avoid doubled-up icons like "✅ ✅ Login confirmed!".
    stripped = msg.lstrip()
    already_has_icon = bool(stripped) and ord(stripped[0]) > 0x2100
    prefix = "" if already_has_icon else f"{icons.get(level, 'ℹ️')} "
    log_buffer.append(f"{prefix}{msg}")
    if len(log_buffer) > 200:
        log_buffer.pop(0)


@app.route("/")
def index():
    with open(os.path.join(BUNDLE_DIR, "index.html"), "r", encoding="utf-8") as f:
        return render_template_string(f.read())


@app.route("/api/config", methods=["GET", "POST"])
def handle_config():
    if request.method == "POST":
        data = request.json
        cfg = load_config()
        cfg.update(data)
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return jsonify({"status": "success", "config": cfg})
    return jsonify(load_config())


@app.route("/api/upload-resume", methods=["POST"])
def upload_resume():
    if "resume" not in request.files:
        return jsonify({"status": "error", "message": "No file uploaded"}), 400
    file = request.files["resume"]
    if file.filename == "":
        return jsonify({"status": "error", "message": "No file selected"}), 400
    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(file_path)
    cfg = load_config()
    cfg["resume_path"] = os.path.abspath(file_path)
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    append_log(f"📁 Resume uploaded: {filename}", "SUCCESS")
    return jsonify({"status": "success", "resume_path": os.path.abspath(file_path)})


@app.route("/api/start", methods=["POST"])
def start_bot():
    global bot_instance, bot_thread, log_buffer
    # Guard the check-then-start sequence with a lock: two near-simultaneous
    # requests (e.g. a double-click) could otherwise both pass the
    # is_alive() check before either thread actually starts, launching two
    # Chrome instances against the same profile dir at once.
    with start_lock:
        if bot_thread and bot_thread.is_alive():
            return jsonify({"status": "already_running", "message": "Bot session is already running."})

        cfg = load_config()
        log_buffer = ["🚀 New session started — resetting counters."]
        bot_instance = NaukriBot(cfg, log_callback=append_log)

        def worker():
            try:
                bot_instance.start()
            except Exception as e:
                append_log(f"Session Error: {e}", "ERROR")

        bot_thread = threading.Thread(target=worker, daemon=True)
        bot_thread.start()
        append_log("🚀 Application session initiated!", "SUCCESS")
    return jsonify({"status": "started", "message": "Session started."})


@app.route("/api/stop", methods=["POST"])
def stop_bot():
    if bot_instance:
        bot_instance.stop()
        append_log("⏸ Stop requested by user.", "WARNING")
        return jsonify({"status": "stop_requested"})
    return jsonify({"status": "not_running"})


@app.route("/api/google-login", methods=["POST"])
def google_login():
    global login_thread
    append_log("🌐 Opening Chrome for login setup...", "INFO")

    def worker():
        try:
            cfg = load_config()
            bot = NaukriBot(cfg, log_callback=append_log)
            bot.ensure_google_login()
        except Exception as e:
            append_log(f"Google Login error: {e}", "ERROR")

    login_thread = threading.Thread(target=worker, daemon=True)
    login_thread.start()
    return jsonify({"status": "opening_chrome", "message": "Chrome window launching. Log into Naukri and keep session open."})


@app.route("/api/manual-login", methods=["POST"])
def manual_login():
    global login_thread
    append_log("💻 Opening Chrome for login setup...", "INFO")

    def worker():
        try:
            cfg = load_config()
            bot = NaukriBot(cfg, log_callback=append_log)
            bot.ensure_login_manual_only()
        except Exception as e:
            append_log(f"Manual Login error: {e}", "ERROR")

    login_thread = threading.Thread(target=worker, daemon=True)
    login_thread.start()
    return jsonify({"status": "opening_chrome", "message": "Chrome window launching. Log into Naukri."})


@app.route("/api/status", methods=["GET"])
def get_status():
    running = bool(bot_thread and bot_thread.is_alive())
    if bot_instance:
        return jsonify({
            "running": running,
            "applied": bot_instance.session_applied,
            "skipped": bot_instance.session_skipped,
            "external": bot_instance.session_external,
            "failed": bot_instance.session_failed,
            "logs": log_buffer[-40:],
        })
    return jsonify({
        "running": running,
        "applied": 0, "skipped": 0, "external": 0, "failed": 0,
        "logs": log_buffer[-40:],
    })


@app.route("/api/report")
def get_report():
    tracker = JobTracker()
    path = tracker.generate_html_report()
    return send_file(path)


def open_browser():
    webbrowser.open("http://localhost:5000")


if __name__ == "__main__":
    print("=" * 55)
    print("  🚀 Naukri Auto-Applier Pro")
    print("     http://localhost:5000")
    print("=" * 55)

    # Check for a newer build before doing anything else — this only does
    # anything in a packaged .exe (a no-op for `python web_app.py` dev
    # runs), and only at startup, so it never interrupts an active session.
    # If an update is applied, this process exits here and a detached
    # helper relaunches the new .exe.
    from updater import check_and_apply_update
    print("  Checking for updates...")
    if check_and_apply_update(BUNDLE_DIR, log=print):
        sys.exit(0)

    threading.Timer(1.5, open_browser).start()
    app.run(host="0.0.0.0", port=5000, debug=False)
