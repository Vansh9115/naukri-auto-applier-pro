import os
import sys
import json
import threading
import webbrowser
from flask import Flask, jsonify, request, send_file, render_template_string
from naukri_bot import NaukriBot, load_config
from tracker import JobTracker

app = Flask(__name__, static_folder=".")

bot_instance = None
bot_thread = None
log_buffer = ["ℹ️ Web Application initialized."]

def append_log(msg, level="INFO"):
    icon_map = {"INFO": "ℹ️", "SUCCESS": "✅", "WARNING": "⚠️", "ERROR": "❌"}
    icon = icon_map.get(level, "ℹ️")
    log_buffer.append(f"{icon} {msg}")
    if len(log_buffer) > 100:
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
    else:
        return jsonify(load_config())

@app.route("/api/start", methods=["POST"])
def start_bot():
    global bot_instance, bot_thread, log_buffer
    if bot_thread and bot_thread.is_alive():
        return jsonify({"status": "already_running"})

    cfg = load_config()
    log_buffer = ["🚀 Starting new application session (counters reset to 0)..."]
    bot_instance = NaukriBot(cfg, log_callback=append_log)

    def _worker():
        try:
            bot_instance.start()
        except Exception as e:
            append_log(f"Execution error: {e}", "ERROR")

    bot_thread = threading.Thread(target=_worker, daemon=True)
    bot_thread.start()
    append_log("🚀 Background auto-application thread started.", "SUCCESS")
    return jsonify({"status": "started"})

@app.route("/api/stop", methods=["POST"])
def stop_bot():
    global bot_instance
    if bot_instance:
        bot_instance.stop()
        append_log("Stop requested by user.", "WARNING")
        return jsonify({"status": "stop_requested"})
    return jsonify({"status": "not_running"})

@app.route("/api/google-login", methods=["POST"])
def google_login():
    def _worker():
        cfg = load_config()
        bot = NaukriBot(cfg, log_callback=append_log)
        bot.ensure_google_login()
    threading.Thread(target=_worker, daemon=True).start()
    append_log("Opening Chrome window for Google Authentication...", "INFO")
    return jsonify({"status": "opening_google_login"})

@app.route("/api/status", methods=["GET"])
def get_status():
    is_running = bool(bot_thread and bot_thread.is_alive())
    
    if bot_instance:
        return jsonify({
            "running": is_running,
            "applied": bot_instance.session_applied,
            "skipped": bot_instance.session_skipped,
            "external": bot_instance.session_external,
            "failed": bot_instance.session_failed,
            "logs": log_buffer[-25:]
        })
    else:
        return jsonify({
            "running": is_running,
            "applied": 0,
            "skipped": 0,
            "external": 0,
            "failed": 0,
            "logs": log_buffer[-25:]
        })

@app.route("/api/report")
def get_report():
    tracker = JobTracker()
    path = tracker.generate_html_report()
    return send_file(path)

def open_browser():
    webbrowser.open("http://localhost:5000")

if __name__ == "__main__":
    print("====================================================")
    print("🚀 Starting Naukri Auto-Applier Pro Web Application")
    print("   Opening browser at http://localhost:5000")
    print("====================================================")
    threading.Timer(1.5, open_browser).start()
    app.run(host="0.0.0.0", port=5000, debug=False)
