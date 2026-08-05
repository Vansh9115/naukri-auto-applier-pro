import os
import sys
import json
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import customtkinter as ctk
from naukri_bot import NaukriBot, load_config
from tracker import JobTracker
from dulwich.repo import Repo
from dulwich import porcelain

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class NaukriAutoApplierApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Naukri Auto-Applier Pro 🚀")
        self.geometry("1150 x 880")
        self.minsize(950, 700)

        self.config_data = load_config("config.json")
        self.bot_thread = None
        self.bot_instance = None

        self.create_layout()
        self.load_settings_into_ui()

    def create_layout(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # --- Header Frame ---
        header_frame = ctk.CTkFrame(self, corner_radius=10, fg_color="#1E1E2E")
        header_frame.grid(row=0, column=0, padx=15, pady=10, sticky="ew")
        header_frame.grid_columnconfigure(1, weight=1)

        app_title = ctk.CTkLabel(
            header_frame, 
            text="Naukri Auto-Applier Pro", 
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#89B4FA"
        )
        app_title.grid(row=0, column=0, padx=15, pady=10, sticky="w")

        self.status_label = ctk.CTkLabel(
            header_frame,
            text="● Status: IDLE",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#A6ADC8"
        )
        self.status_label.grid(row=0, column=1, padx=15, pady=10, sticky="e")

        # --- Main Body Frame ---
        body_frame = ctk.CTkFrame(self, fg_color="transparent")
        body_frame.grid(row=1, column=0, padx=15, pady=5, sticky="nsew")
        body_frame.grid_columnconfigure(0, weight=4)
        body_frame.grid_columnconfigure(1, weight=6)
        body_frame.grid_rowconfigure(0, weight=1)

        # --- Left Panel: Settings Form ---
        settings_scroll = ctk.CTkScrollableFrame(body_frame, label_text="⚙️ User Credentials & Profile Parameters", corner_radius=10)
        settings_scroll.grid(row=0, column=0, padx=(0, 10), pady=0, sticky="nsew")

        # Naukri Credentials
        ctk.CTkLabel(settings_scroll, text="🔑 Naukri Email / Username (Optional for Auto-Login):", font=ctk.CTkFont(size=12, weight="bold"), text_color="#89B4FA").pack(anchor="w", pady=(5, 2))
        self.email_entry = ctk.CTkEntry(settings_scroll, placeholder_text="your_email@example.com")
        self.email_entry.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(settings_scroll, text="🔑 Naukri Password (Optional for Auto-Login):", font=ctk.CTkFont(size=12, weight="bold"), text_color="#89B4FA").pack(anchor="w", pady=(5, 2))
        self.pwd_entry = ctk.CTkEntry(settings_scroll, placeholder_text="••••••••", show="•")
        self.pwd_entry.pack(fill="x", pady=(0, 10))

        # GitHub Personal Access Token
        ctk.CTkLabel(settings_scroll, text="🐙 GitHub Personal Access Token (for Code Sync):", font=ctk.CTkFont(size=12, weight="bold"), text_color="#FAB387").pack(anchor="w", pady=(5, 2))
        self.github_token_entry = ctk.CTkEntry(settings_scroll, placeholder_text="ghp_xxxxxxxxxxxxxxxxxxxx", show="•")
        self.github_token_entry.pack(fill="x", pady=(0, 10))

        # Job Keywords
        ctk.CTkLabel(settings_scroll, text="Target Job Keywords (comma-separated):", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(5, 2))
        self.kw_entry = ctk.CTkEntry(settings_scroll, placeholder_text="e.g. Operation Management, Finance, AML")
        self.kw_entry.pack(fill="x", pady=(0, 10))

        # Target Locations
        ctk.CTkLabel(settings_scroll, text="Target Locations (comma-separated):", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(5, 2))
        self.loc_entry = ctk.CTkEntry(settings_scroll, placeholder_text="e.g. Bangalore, Gurugram, Delhi NCR, Remote")
        self.loc_entry.pack(fill="x", pady=(0, 10))

        # Experience (Years)
        ctk.CTkLabel(settings_scroll, text="Total Work Experience (Years):", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(5, 2))
        self.exp_entry = ctk.CTkEntry(settings_scroll, placeholder_text="4")
        self.exp_entry.pack(fill="x", pady=(0, 10))

        # Current CTC & Expected CTC
        ctk.CTkLabel(settings_scroll, text="Current CTC (in LPA):", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(5, 2))
        self.curr_ctc_entry = ctk.CTkEntry(settings_scroll, placeholder_text="4.0")
        self.curr_ctc_entry.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(settings_scroll, text="Expected CTC (in LPA):", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(5, 2))
        self.exp_ctc_entry = ctk.CTkEntry(settings_scroll, placeholder_text="6.5")
        self.exp_ctc_entry.pack(fill="x", pady=(0, 10))

        # Notice Period
        ctk.CTkLabel(settings_scroll, text="Notice Period:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(5, 2))
        self.notice_menu = ctk.CTkOptionMenu(
            settings_scroll, 
            values=["15 Days or less", "Immediate", "30 Days", "60 Days", "90 Days"]
        )
        self.notice_menu.pack(fill="x", pady=(0, 10))

        # Resume File Picker
        ctk.CTkLabel(settings_scroll, text="Resume PDF File Path:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(5, 2))
        resume_frame = ctk.CTkFrame(settings_scroll, fg_color="transparent")
        resume_frame.pack(fill="x", pady=(0, 10))
        self.resume_entry = ctk.CTkEntry(resume_frame, placeholder_text="C:/path/to/resume.pdf")
        self.resume_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        browse_btn = ctk.CTkButton(resume_frame, text="Browse...", width=70, command=self.browse_resume)
        browse_btn.pack(side="right")

        # Switches / Options
        self.relocate_switch = ctk.CTkSwitch(settings_scroll, text="Willing to Relocate / Travel")
        self.relocate_switch.pack(anchor="w", pady=(5, 10))

        self.headless_switch = ctk.CTkSwitch(settings_scroll, text="Run Browser in Background (Headless)")
        self.headless_switch.pack(anchor="w", pady=(5, 10))

        # Max Applications Limit
        ctk.CTkLabel(settings_scroll, text="Max Applications Per Run:", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(5, 2))
        self.max_apps_entry = ctk.CTkEntry(settings_scroll, placeholder_text="30")
        self.max_apps_entry.pack(fill="x", pady=(0, 15))

        # --- Control Action Buttons ---
        btn_frame = ctk.CTkFrame(settings_scroll, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(5, 10))

        self.start_btn = ctk.CTkButton(
            btn_frame, 
            text="🚀 Save & Start Applying", 
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#A6E3A1",
            text_color="#11111B",
            hover_color="#94E2D5",
            command=self.start_application_process
        )
        self.start_btn.pack(fill="x", pady=(0, 8))

        self.stop_btn = ctk.CTkButton(
            btn_frame, 
            text="⏸ Stop Application Bot", 
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#F38BA8",
            text_color="#11111B",
            hover_color="#EBA0AC",
            command=self.stop_application_process,
            state="disabled"
        )
        self.stop_btn.pack(fill="x", pady=(0, 8))

        self.login_btn = ctk.CTkButton(
            btn_frame, 
            text="🌐 Open Chrome & Log In To Naukri", 
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#89B4FA",
            text_color="#11111B",
            hover_color="#B4BEFE",
            command=self.open_login_window
        )
        self.login_btn.pack(fill="x", pady=(0, 8))

        self.report_btn = ctk.CTkButton(
            btn_frame, 
            text="📊 View Analytics & HTML Report", 
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#CBA6F7",
            text_color="#11111B",
            hover_color="#F5C2E7",
            command=self.show_analytics_report
        )
        self.report_btn.pack(fill="x", pady=(0, 8))

        self.github_btn = ctk.CTkButton(
            btn_frame, 
            text="🐙 Sync & Push Code to GitHub", 
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#FAB387",
            text_color="#11111B",
            hover_color="#F9E2AF",
            command=self.push_to_github_ui
        )
        self.github_btn.pack(fill="x", pady=(0, 5))

        # --- Right Panel: Live Activity Log Console ---
        console_frame = ctk.CTkFrame(body_frame, corner_radius=10)
        console_frame.grid(row=0, column=1, padx=(10, 0), pady=0, sticky="nsew")
        console_frame.grid_rowconfigure(1, weight=1)
        console_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            console_frame, 
            text="📋 Live Activity Log & Execution Output", 
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, padx=10, pady=10, sticky="w")

        self.log_textbox = ctk.CTkTextbox(
            console_frame, 
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word"
        )
        self.log_textbox.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")

    def browse_resume(self):
        file_path = filedialog.askopenfilename(
            title="Select Resume PDF File",
            filetypes=[("PDF files", "*.pdf"), ("Word documents", "*.docx"), ("All files", "*.*")]
        )
        if file_path:
            self.resume_entry.delete(0, tk.END)
            self.resume_entry.insert(0, file_path)

    def load_settings_into_ui(self):
        cfg = self.config_data
        
        if cfg.get("naukri_email"):
            self.email_entry.insert(0, cfg.get("naukri_email"))
        if cfg.get("naukri_password"):
            self.pwd_entry.insert(0, cfg.get("naukri_password"))
        if cfg.get("github_token"):
            self.github_token_entry.insert(0, cfg.get("github_token"))

        kw_list = cfg.get("keywords", ["Operation Management", "Finance", "AML"])
        self.kw_entry.insert(0, ", ".join(kw_list))

        loc_list = cfg.get("locations", ["Bangalore", "Gurugram", "Delhi NCR", "Noida", "Hyderabad", "Pune"])
        self.loc_entry.insert(0, ", ".join(loc_list))

        self.exp_entry.insert(0, str(cfg.get("experience_years", 4)))
        self.curr_ctc_entry.insert(0, str(cfg.get("current_ctc_lpa", 4.0)))
        self.exp_ctc_entry.insert(0, str(cfg.get("expected_ctc_lpa", 6.5)))
        self.notice_menu.set(cfg.get("notice_period_str", "15 Days or less"))
        
        if cfg.get("resume_path"):
            self.resume_entry.insert(0, cfg.get("resume_path"))
            
        if cfg.get("willing_to_relocate", True):
            self.relocate_switch.select()
            
        if cfg.get("headless", False):
            self.headless_switch.select()
            
        self.max_apps_entry.insert(0, str(cfg.get("max_applications_per_run", 30)))

    def save_settings_from_ui(self):
        keywords = [k.strip() for k in self.kw_entry.get().split(",") if k.strip()]
        locations = [l.strip() for l in self.loc_entry.get().split(",") if l.strip()]

        notice_str = self.notice_menu.get()
        notice_days = 15
        if "Immediate" in notice_str:
            notice_days = 0
        elif "30" in notice_str:
            notice_days = 30
        elif "60" in notice_str:
            notice_days = 60
        elif "90" in notice_str:
            notice_days = 90

        cfg = {
            "naukri_email": self.email_entry.get().strip(),
            "naukri_password": self.pwd_entry.get().strip(),
            "github_token": self.github_token_entry.get().strip(),
            "keywords": keywords if keywords else ["Operations Management"],
            "locations": locations if locations else ["Bangalore"],
            "experience_years": int(self.exp_entry.get().strip() or "4"),
            "current_ctc_lpa": float(self.curr_ctc_entry.get().strip() or "4.0"),
            "expected_ctc_lpa": float(self.exp_ctc_entry.get().strip() or "6.5"),
            "notice_period_days": notice_days,
            "notice_period_str": notice_str,
            "resume_path": self.resume_entry.get().strip(),
            "willing_to_relocate": bool(self.relocate_switch.get()),
            "max_applications_per_run": int(self.max_apps_entry.get().strip() or "30"),
            "headless": bool(self.headless_switch.get()),
            "delay_between_jobs_seconds": [3, 6],
            "chrome_user_data_dir": "./naukri_user_data",
            "log_file": "applied_jobs.csv"
        }

        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)

        self.config_data = cfg
        self.log_to_console("System settings saved to config.json", "SUCCESS")

    def log_to_console(self, text, level="INFO"):
        def _update():
            icon_map = {"INFO": "ℹ️", "SUCCESS": "✅", "WARNING": "⚠️", "ERROR": "❌"}
            icon = icon_map.get(level, "ℹ️")
            log_line = f"{icon} {text}\n"
            self.log_textbox.insert(tk.END, log_line)
            self.log_textbox.see(tk.END)
        self.after(0, _update)

    def start_application_process(self):
        try:
            self.save_settings_from_ui()
        except Exception as ex:
            messagebox.showerror("Invalid Input", f"Please check input parameters:\n{ex}")
            return

        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.status_label.configure(text="● Status: RUNNING", text_color="#A6E3A1")
        self.log_textbox.delete("1.0", tk.END)

        self.bot_instance = NaukriBot(self.config_data, log_callback=self.log_to_console)

        def _run_worker():
            try:
                self.bot_instance.start()
            except Exception as ex:
                self.log_to_console(f"Automation execution error: {ex}", "ERROR")
            finally:
                self.after(0, self.on_bot_finished)

        self.bot_thread = threading.Thread(target=_run_worker, daemon=True)
        self.bot_thread.start()

    def stop_application_process(self):
        if self.bot_instance:
            self.bot_instance.stop()
            self.log_to_console("Stopping bot requested by user...", "WARNING")
        self.stop_btn.configure(state="disabled")

    def on_bot_finished(self):
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.status_label.configure(text="● Status: IDLE", text_color="#A6ADC8")
        
        tracker = JobTracker()
        summary = tracker.get_analytics_summary()
        self.log_to_console("\n" + "="*50, "SUCCESS")
        self.log_to_console("📊 POST-RUN APPLICATION ANALYTICS", "SUCCESS")
        self.log_to_console(f"  • Total Jobs Logged: {summary['total']}", "INFO")
        self.log_to_console(f"  • Successfully Applied: {summary['applied']}", "SUCCESS")
        self.log_to_console(f"  • Already Applied (Skipped): {summary['already_applied']}", "WARNING")
        self.log_to_console(f"  • External Site Redirects: {summary['external']}", "INFO")
        self.log_to_console(f"  • Failed / Missing Button: {summary['failed']}", "ERROR")
        self.log_to_console("="*50 + "\n", "SUCCESS")

    def show_analytics_report(self):
        tracker = JobTracker()
        report_path = tracker.generate_html_report()
        summary = tracker.get_analytics_summary()
        
        webbrowser.open(f"file:///{report_path}")
        
        msg = f"""📊 Application Analytics Summary:

✅ Successfully Applied: {summary['applied']}
⚠️ Already Applied / Skipped: {summary['already_applied']}
ℹ️ External Site Redirects: {summary['external']}
❌ Failed / Missing Button: {summary['failed']}

Total Jobs Logged: {summary['total']}

The interactive HTML Analytics Report has been opened in your browser!"""
        messagebox.showinfo("Application Analytics Report", msg)

    def push_to_github_ui(self):
        self.save_settings_from_ui()
        def _github_worker():
            repo_path = os.path.abspath(".")
            if not os.path.exists(os.path.join(repo_path, '.git')):
                repo = Repo.init(repo_path)
            else:
                repo = Repo(repo_path)

            target_url = "https://github.com/Vansh9115/naukri-auto-applier-pro.git"
            cfg = repo.get_config()
            cfg.set(("remote", "origin"), "url", target_url.encode('utf-8'))
            cfg.write_to_path()

            self.log_to_console("Staging project files for GitHub sync...", "INFO")
            porcelain.add(repo)
            try:
                commit_id = porcelain.commit(repo, message=b"Sync software update from desktop app")
                self.log_to_console(f"Committed changes: {commit_id.decode()[:7]}", "SUCCESS")
            except Exception as e:
                self.log_to_console(f"Commit note: {e}", "INFO")

            pat = self.config_data.get("github_token", "").strip()
            if not pat:
                pat = simpledialog.askstring("GitHub Sync", "Enter your GitHub Personal Access Token (PAT):\n\n(Create one at https://github.com/settings/tokens with 'repo' scope)", show="•")
                if pat:
                    self.config_data["github_token"] = pat.strip()
                    with open("config.json", "w", encoding="utf-8") as f:
                        json.dump(self.config_data, f, indent=2)

            if pat and pat.strip():
                auth_url = f"https://Vansh9115:{pat.strip()}@github.com/Vansh9115/naukri-auto-applier-pro.git"
                try:
                    self.log_to_console("Pushing commits to GitHub repository...", "INFO")
                    porcelain.push(repo, auth_url, "refs/heads/main")
                    self.log_to_console("🎉 SUCCESS! Pushed repository to https://github.com/Vansh9115/naukri-auto-applier-pro", "SUCCESS")
                    messagebox.showinfo("GitHub Sync Success", "Repository successfully synced and pushed to GitHub!\n\nhttps://github.com/Vansh9115/naukri-auto-applier-pro")
                except Exception as ex:
                    self.log_to_console(f"Push error: {ex}", "ERROR")
                    messagebox.showerror("GitHub Push Error", f"Failed to push to GitHub:\n{ex}\n\nPlease check token permissions.")
            else:
                self.log_to_console("Push cancelled: GitHub token not provided.", "WARNING")

        threading.Thread(target=_github_worker, daemon=True).start()

    def open_login_window(self):
        self.save_settings_from_ui()
        self.log_to_console("Opening Chrome browser window for Naukri login setup...", "INFO")
        def _login_worker():
            bot = NaukriBot(self.config_data, log_callback=self.log_to_console)
            bot.ensure_login_manual_only()
        threading.Thread(target=_login_worker, daemon=True).start()

if __name__ == "__main__":
    app = NaukriAutoApplierApp()
    app.mainloop()
