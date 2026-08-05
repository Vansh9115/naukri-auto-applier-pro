import os
import sys
import json
import threading
import webbrowser
from flask import Flask, jsonify, request, send_file, render_template_string
from werkzeug.utils import secure_filename
from naukri_bot import NaukriBot, load_config
from tracker import JobTracker

app = Flask(__name__, static_folder=".")
app.config["UPLOAD_FOLDER"] = os.path.abspath("./uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

bot_instance = None
bot_thread = None
login_thread = None
log_buffer = []


def append_log(msg, level="INFO"):
    icons = {"INFO": "ℹ️", "SUCCESS": "✅", "WARNING": "⚠️", "ERROR": "❌"}
    log_buffer.append(f"{icons.get(level, 'ℹ️')} {msg}")
    if len(log_buffer) > 150:
        log_buffer.pop(0)


@app.route("/")
def index():
    with open("index.html", "r", encoding="utf-8") as f:
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
    if bot_thread and bot_thread.is_alive():
        return jsonify({"status": "already_running"})
    cfg = load_config()
    log_buffer = ["🚀 New session — counters reset to 0."]
    bot_instance = NaukriBot(cfg, log_callback=append_log)

    def worker():
        try:
            bot_instance.start()
        except Exception as e:
            append_log(f"Engine error: {e}", "ERROR")

    bot_thread = threading.Thread(target=worker, daemon=True)
    bot_thread.start()
    return jsonify({"status": "started"})


@app.route("/api/stop", methods=["POST"])
def stop_bot():
    if bot_instance:
        bot_instance.stop()
        append_log("⏸ Stop requested.", "WARNING")
        return jsonify({"status": "stop_requested"})
    return jsonify({"status": "not_running"})


@app.route("/api/google-login", methods=["POST"])
def google_login():
    global login_thread
    append_log("🌐 Launching Chrome for Google sign-in...", "INFO")
    append_log("👉 A Chrome window will open. Sign in with Google on Naukri.", "INFO")
    append_log("👉 After logging in, CLOSE the Chrome window to save your session.", "INFO")

    def worker():
        try:
            cfg = load_config()
            bot = NaukriBot(cfg, log_callback=append_log)
            bot.ensure_google_login()
        except Exception as e:
            append_log(f"Login error: {e}", "ERROR")

    login_thread = threading.Thread(target=worker, daemon=True)
    login_thread.start()
    return jsonify({"status": "opening_chrome", "message": "Chrome is opening. Sign in with Google, then CLOSE Chrome."})


@app.route("/api/manual-login", methods=["POST"])
def manual_login():
    global login_thread
    append_log("💻 Launching Chrome for email login...", "INFO")
    append_log("👉 A Chrome window will open. Log in with email & password.", "INFO")
    append_log("👉 After logging in, CLOSE the Chrome window.", "INFO")

    def worker():
        try:
            cfg = load_config()
            bot = NaukriBot(cfg, log_callback=append_log)
            bot.ensure_login_manual_only()
        except Exception as e:
            append_log(f"Login error: {e}", "ERROR")

    login_thread = threading.Thread(target=worker, daemon=True)
    login_thread.start()
    return jsonify({"status": "opening_chrome", "message": "Chrome is opening. Log in, then CLOSE Chrome."})


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
    threading.Timer(1.5, open_browser).start()
    app.run(host="0.0.0.0", port=5000, debug=False)
