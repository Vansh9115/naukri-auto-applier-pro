import os
import sys
import json
import time
import random
import subprocess
import urllib.parse
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from tracker import JobTracker

def load_config(config_path="config.json"):
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Smart Answer Engine
# ---------------------------------------------------------------------------

class SmartAnswerEngine:
    """
    Determines the right answer for ANY Naukri chatbot question.

    Key insight from live Naukri chatbot:
      - Questions appear as chat bubbles like "Total IT Experience? (in YY/MM)"
      - User must type answer in a single text input with placeholder "Type message here..."
      - Some ask for YY/MM format, some ask for just a number, some are free text
    """

    def __init__(self, config):
        self.exp = config.get("experience_years", 4)
        self.curr_ctc = config.get("current_ctc_lpa", 4.0)
        self.exp_ctc = config.get("expected_ctc_lpa", 6.5)
        self.notice_days = config.get("notice_period_days", 15)
        self.notice_str = config.get("notice_period_str", "15 Days or less")
        self.locations = config.get("locations", ["Bangalore"])
        self.relocate = config.get("willing_to_relocate", True)
        self.gender = config.get("gender", "Male")
        self.degree = config.get("degree", "B.Com")

    def answer_question(self, question_text: str) -> str:
        """Given any chatbot question text, return the best answer string."""
        q = question_text.lower().strip()

        # ── YY/MM format explicitly requested ──
        if "yy/mm" in q or "yy /mm" in q or "years/months" in q:
            return f"{self.exp:02d}/00"

        # ── CTC questions (check BEFORE experience since CTC questions
        #    sometimes contain the word "experience") ──
        if any(k in q for k in [
            "current ctc", "present ctc", "current salary", "present salary",
            "current annual", "annual ctc", "last drawn", "current compensation",
            "existing ctc", "current package", "ctc in lpa",
        ]):
            return str(self.curr_ctc)

        if any(k in q for k in [
            "expected ctc", "expected salary", "desired ctc", "desired salary",
            "expected annual", "expected compensation", "expected package",
        ]):
            return str(self.exp_ctc)

        # ── Notice period ──
        if any(k in q for k in [
            "notice period", "notice", "days to join", "joining time",
            "time to join", "when can you join", "earliest joining",
        ]):
            return str(self.notice_days)

        # ── Location ──
        if any(k in q for k in [
            "current location", "current city", "preferred location",
            "where are you", "which city",
        ]):
            return self.locations[0] if self.locations else "Bangalore"

        # ── Relocation ──
        if any(k in q for k in ["relocat", "willing to relocate", "ready to move"]):
            return "Yes" if self.relocate else "No"

        # ── Gender ──
        if any(k in q for k in ["gender", "sex"]):
            return self.gender

        # ── Education ──
        if any(k in q for k in ["graduation", "degree", "qualification", "education"]):
            return self.degree

        # ── Age ──
        if any(k in q for k in ["age", "date of birth", "dob"]):
            return "25"

        # ── ANY experience / years / skill question ──
        # This is the CATCH-ALL: Naukri's chatbot mostly asks
        # "How many years of experience do you have in <SKILL>?"
        # or "Total IT Experience?" etc.
        # Safe default: return the experience years number.
        if any(k in q for k in [
            "experience", "years", "year", "exp", "how many",
            "how long", "duration", "total",
            # Technology / skill names (bot asks experience in these)
            "python", "java", "javascript", "react", "angular", "node",
            "sql", "mysql", "oracle", "mongodb",
            "aws", "azure", "gcp", "cloud", "devops", "docker", "kubernetes",
            "linux", "windows", "networking", "firewall", "cisco", "juniper",
            "switch", "router", "vlan", "bgp", "ospf",
            "machine learning", "data", "analytics", "tableau", "power bi",
            "excel", "sap", "salesforce", "servicenow",
            "project management", "agile", "scrum", "team lead",
            "finance", "accounts", "audit", "compliance", "aml", "kyc",
            "operations", "supply chain", "logistics", "procurement",
            "communication", "leadership", "management",
            "testing", "automation", "selenium", "manual testing",
            "html", "css", "php", "c++", "c#", ".net", "ruby",
            "android", "ios", "flutter", "react native",
            "arista", "eos", "vxlan", "evpn", "ansible",
        ]):
            return str(self.exp)

        # ── Absolute fallback: experience years (safest numeric answer) ──
        return str(self.exp)

    def pick_radio(self, option_text: str) -> bool:
        """Return True if this radio/chip/option should be selected."""
        t = option_text.lower().strip()
        exp = self.exp

        # Experience range
        if any(s in t for s in [
            f"{exp} year", f"{exp} yr", f"{exp}+",
            "3-5", "4-5", "3-6", "4-6", "2-5", "3-7", "4-8",
        ]):
            return True

        # Notice period
        if any(s in t for s in [
            "15 day", "15 days or less", "immediate", "less than 15",
            "1 month", "within 15",
        ]):
            return True

        # Relocation
        if self.relocate and t in ("yes", "ready to relocate", "willing to relocate"):
            return True

        # Location
        if any(loc.lower() in t for loc in self.locations):
            return True

        # Gender
        if t == self.gender.lower():
            return True

        return False


# ---------------------------------------------------------------------------
# Main Bot
# ---------------------------------------------------------------------------

class NaukriBot:
    def __init__(self, config=None, log_callback=None):
        self.config = config or load_config()
        self.tracker = JobTracker(self.config.get("log_file", "applied_jobs.csv"))
        self.answer_engine = SmartAnswerEngine(self.config)

        # Session counters (reset per session)
        self.session_applied = 0
        self.session_skipped = 0
        self.session_failed = 0
        self.session_external = 0

        self.stop_requested = False
        self.log_callback = log_callback
        self.user_data_dir = os.path.abspath(
            self.config.get("chrome_user_data_dir", "./naukri_user_data")
        )
        Path(self.user_data_dir).mkdir(parents=True, exist_ok=True)

    def log(self, msg, level="INFO"):
        print(f"[{level}] {msg}")
        if self.log_callback:
            try:
                self.log_callback(msg, level)
            except Exception:
                pass

    def _cleanup_locks(self, path):
        for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            f = os.path.join(path, name)
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

    def random_sleep(self, lo=None, hi=None):
        if lo is None or hi is None:
            d = self.config.get("delay_between_jobs_seconds", [3, 6])
            lo, hi = d[0], d[1]
        time.sleep(random.uniform(lo, hi))

    def stop(self):
        self.stop_requested = True
        self.log("Stop requested.", "WARNING")

    # ── Browser creation (ALWAYS visible, shared session dir) ─────────
    def _create_context(self, p):
        self._cleanup_locks(self.user_data_dir)
        args = [
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
            "--no-sandbox",
            "--disable-notifications",
            "--deny-permission-prompts",
            "--hide-crash-restore-bubble",
            "--disable-session-crashed-bubble",
            "--disable-infobars",
            "--window-position=50,50",
            "--window-size=1300,900",
        ]

        def _try_launch(d):
            return p.chromium.launch_persistent_context(
                user_data_dir=d, headless=False, args=args, no_viewport=True,
            )

        try:
            return _try_launch(self.user_data_dir)
        except Exception as e:
            self.log(f"Profile lock ({e}). Trying fallback dir...", "WARNING")
            fb = os.path.abspath("./naukri_user_data_session")
            Path(fb).mkdir(parents=True, exist_ok=True)
            self._cleanup_locks(fb)
            return _try_launch(fb)

    # ── Google Login (uses Playwright so session is shared) ────────────
    def ensure_google_login(self):
        """
        Opens a VISIBLE Playwright Chrome window to Naukri login page.
        The user clicks 'Google' on Naukri's page, completes OAuth,
        and the session cookies are saved in the persistent context.
        """
        self.log("🌐 Opening Chrome for Google login to Naukri...", "INFO")
        with sync_playwright() as p:
            ctx = self._create_context(p)
            pg = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                pg.bring_to_front()
            except Exception:
                pass
            pg.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded")
            self.random_sleep(2, 3)

            # Try to find and click the Google sign-in button on Naukri's page
            try:
                google_selectors = [
                    "button:has-text('Google')",
                    "a:has-text('Google')",
                    "div[class*='google']",
                    "button[class*='google']",
                    "a[class*='google']",
                    "div[class*='Google']",
                    "button[aria-label*='Google']",
                    "img[alt*='Google']",
                    ".google-login-btn",
                    "span:has-text('Google')",
                ]
                for sel in google_selectors:
                    el = pg.query_selector(sel)
                    if el and el.is_visible():
                        el.click()
                        self.log("Clicked Google sign-in button on Naukri.", "SUCCESS")
                        break
            except Exception:
                pass

            self.log("🌐 Chrome is open! Complete Google sign-in in the browser.", "SUCCESS")
            self.log("Close the Chrome window when you're done logging in.", "INFO")

            # Keep alive until user closes all pages
            try:
                while len(ctx.pages) > 0:
                    time.sleep(2)
            except Exception:
                pass

            try:
                ctx.close()
            except Exception:
                pass

        self.log("✅ Login session saved! You can now start applying.", "SUCCESS")

    def ensure_login_manual_only(self):
        """Opens Chrome to Naukri login for email/password."""
        self.log("💻 Opening Chrome for Naukri email login...", "INFO")
        with sync_playwright() as p:
            ctx = self._create_context(p)
            pg = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                pg.bring_to_front()
            except Exception:
                pass
            pg.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded")
            self.log("💻 Chrome is open! Log in and close the window when done.", "SUCCESS")

            try:
                while len(ctx.pages) > 0:
                    time.sleep(2)
            except Exception:
                pass

            try:
                ctx.close()
            except Exception:
                pass

        self.log("✅ Login session saved!", "SUCCESS")

    # ── Login check ───────────────────────────────────────────────────
    def _is_logged_in(self, page, context):
        try:
            url = page.url.lower()
            if any(x in url for x in ["mnjuser/homepage", "mnjuser/profile", "naukri.com/mnjuser"]):
                return True
            el = page.query_selector(
                ".nI-gD-profile, .profile-edit, a[href*='mnjuser/profile'], "
                ".user-name, div[class*='nI-gD']"
            )
            if el and el.is_visible():
                return True
            for c in context.cookies():
                if c.get("name") in ("nls", "Naukri_User", "n_user", "nauk_at"):
                    return True
        except Exception:
            pass
        return False

    def _ensure_login(self, page, context):
        self.log("Checking Naukri login...")
        try:
            page.goto("https://www.naukri.com/mnjuser/homepage", wait_until="domcontentloaded")
            self.random_sleep(2, 3)
        except Exception as e:
            self.log(f"Navigation error: {e}", "ERROR")
            return False

        if self._is_logged_in(page, context):
            self.log("✅ Logged in!", "SUCCESS")
            return True

        # Try navigating to login page
        try:
            page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded")
            self.random_sleep(2, 3)
        except Exception:
            pass

        # Auto-fill credentials
        email = self.config.get("naukri_email", "").strip()
        pwd = self.config.get("naukri_password", "").strip()
        if email and pwd:
            self.log(f"🔑 Auto-login for '{email}'...")
            try:
                u = page.query_selector("#usernameField, input[placeholder*='Email'], input[name*='email']")
                if u:
                    u.fill(email)
                    self.random_sleep(0.5, 1)
                pw = page.query_selector("#passwordField, input[type='password']")
                if pw:
                    pw.fill(pwd)
                    self.random_sleep(0.5, 1)
                b = page.query_selector("button[type='submit'], button:has-text('Login')")
                if b:
                    b.click()
                    self.random_sleep(3, 5)
            except Exception:
                pass

        if self._is_logged_in(page, context):
            self.log("✅ Logged in via credentials!", "SUCCESS")
            return True

        self.log("⏳ Waiting for you to login (up to 3 min)...", "INFO")
        for _ in range(60):
            if self.stop_requested:
                return False
            time.sleep(3)
            if self._is_logged_in(page, context):
                self.log("✅ Login detected!", "SUCCESS")
                return True

        self.log("Login timeout.", "ERROR")
        return False

    # ── Main entry point ──────────────────────────────────────────────
    def start(self):
        self.session_applied = 0
        self.session_skipped = 0
        self.session_failed = 0
        self.session_external = 0
        self.stop_requested = False
        self.log("🚀 Starting Auto-Application Session...")

        with sync_playwright() as p:
            context = self._create_context(p)
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.bring_to_front()
            except Exception:
                pass

            if not self._ensure_login(page, context):
                self.log("Login failed. Please use 'Login with Google' or 'Login with Email' first.", "ERROR")
                try:
                    context.close()
                except Exception:
                    pass
                return

            keywords = self.config.get("keywords", ["Operations Management"])
            max_apps = self.config.get("max_applications_per_run", 30)

            for kw in keywords:
                if self.stop_requested or self.session_applied >= max_apps:
                    break
                self.log(f"\n🔍 Searching: '{kw}'")
                self._process_keyword(page, kw)

            self.log(
                f"\n🏁 Session Done: Applied={self.session_applied} "
                f"Skipped={self.session_skipped} External={self.session_external} "
                f"Failed={self.session_failed}",
                "SUCCESS",
            )
            try:
                context.close()
            except Exception:
                pass

    # ── Search ────────────────────────────────────────────────────────
    def _process_keyword(self, page, keyword):
        locs = ",".join(self.config.get("locations", []))
        exp = self.config.get("experience_years", 4)
        url = (
            f"https://www.naukri.com/{keyword.lower().replace(' ', '-')}-jobs?"
            f"k={urllib.parse.quote(keyword)}&l={urllib.parse.quote(locs)}"
            f"&experience={exp}"
        )
        self.log(f"Loading: {url}")
        try:
            page.goto(url, wait_until="domcontentloaded")
            self.random_sleep(3, 5)
        except Exception as e:
            self.log(f"Search error: {e}", "ERROR")
            return

        for pg_num in range(1, 6):
            if self.stop_requested or self.session_applied >= self.config.get("max_applications_per_run", 30):
                break

            self.log(f"  Page {pg_num} for '{keyword}'...")
            try:
                page.wait_for_selector(".srp-jobtuple-wrapper, article.jobTuple, .cust-job-tuple", timeout=8000)
            except Exception:
                self.log(f"  No jobs on page {pg_num}.", "WARNING")
                break

            cards = page.query_selector_all(".srp-jobtuple-wrapper, article.jobTuple, .cust-job-tuple")
            self.log(f"  Found {len(cards)} job cards.")

            jobs = []
            for card in cards:
                try:
                    a = card.query_selector("a.title, a.title.ellipsis")
                    if not a:
                        continue
                    href = a.get_attribute("href")
                    title = a.text_content().strip()
                    comp_el = card.query_selector("a.subTitle, span.comp-name")
                    company = comp_el.text_content().strip() if comp_el else "Unknown"
                    jid = card.get_attribute("data-job-id") or href

                    badge = card.query_selector(".already-applied, span:has-text('Applied'), .applied-badge")
                    if badge or self.tracker.is_applied(jid, href, title, company):
                        self.session_skipped += 1
                        continue
                    jobs.append({"id": jid, "title": title, "company": company, "url": href})
                except Exception:
                    continue

            for job in jobs:
                if self.stop_requested or self.session_applied >= self.config.get("max_applications_per_run", 30):
                    break
                self._apply_to_job(page.context, job)
                self.random_sleep()

            try:
                nxt = page.query_selector("a:has-text('Next')")
                if nxt and nxt.is_visible():
                    nxt.click()
                    self.random_sleep(3, 5)
                else:
                    break
            except Exception:
                break

    # ── Apply to a single job ─────────────────────────────────────────
    def _apply_to_job(self, context, job):
        self.log(f"👉 {job['title']} @ {job['company']}")
        pg = context.new_page()
        try:
            pg.goto(job["url"], wait_until="domcontentloaded")
            self.random_sleep(2, 3)

            apply_btn = pg.query_selector(
                "button#apply-button, button.apply-button, "
                "button:has-text('Apply'), "
                ".apply-button-container button"
            )

            if not apply_btn:
                already = pg.query_selector(".already-applied, span:has-text('Already Applied'), .applied-msg")
                if already:
                    self.log("  ↩ Already applied.", "INFO")
                    self.tracker.log_application(job["id"], job["title"], job["company"], "", job["url"], status="ALREADY_APPLIED")
                    self.session_skipped += 1
                else:
                    self.log("  ⚠ No Apply button.", "WARNING")
                    self.tracker.log_application(job["id"], job["title"], job["company"], "", job["url"], status="SKIPPED", notes="No Apply button")
                    self.session_skipped += 1
                pg.close()
                return

            btn_text = (apply_btn.text_content() or "").strip().lower()

            # ── ONLY skip jobs that redirect to company career portal ──
            if any(ext in btn_text for ext in ["company site", "company website", "external", "apply on company"]):
                self.log(f"  ⏭ External portal redirect. Skipping.", "INFO")
                self.tracker.log_application(job["id"], job["title"], job["company"], "", job["url"], status="EXTERNAL", notes=btn_text)
                self.session_external += 1
                pg.close()
                return

            self.log(f"  Clicking Apply...")
            apply_btn.click()
            self.random_sleep(2, 4)

            # Check if redirected to external site
            current_url = pg.url.lower()
            if "naukri.com" not in current_url and "naukri" not in current_url:
                self.log(f"  ⏭ Redirected outside Naukri. Skipping.", "INFO")
                self.tracker.log_application(job["id"], job["title"], job["company"], "", job["url"], status="EXTERNAL", notes="Redirected to external domain")
                self.session_external += 1
                pg.close()
                return

            # Solve chatbot / questionnaire
            self._solve_chatbot_and_forms(pg, job)

            self.log(f"  🎯 Applied: {job['title']} @ {job['company']}", "SUCCESS")
            self.tracker.log_application(job["id"], job["title"], job["company"], "", job["url"], status="APPLIED")
            self.session_applied += 1

        except Exception as e:
            self.log(f"  ❌ Error: {e}", "ERROR")
            self.tracker.log_application(job["id"], job["title"], job["company"], "", job["url"], status="FAILED", notes=str(e)[:120])
            self.session_failed += 1
        finally:
            try:
                pg.close()
            except Exception:
                pass

    # ──────────────────────────────────────────────────────────────────
    # CHATBOT + FORM SOLVER
    # This is the core intelligence that fills Naukri's chatbot prompts
    # like "Total IT Experience? (in YY/MM)" and all other questionnaire
    # forms, radio buttons, dropdowns, file uploads, etc.
    # ──────────────────────────────────────────────────────────────────

    def _solve_chatbot_and_forms(self, page, job):
        """
        Iteratively solves up to 15 rounds of Naukri chatbot questions
        and form-based questionnaires. NEVER skips — fills everything.
        """
        resume_file = self.config.get("resume_path", "")

        for step in range(1, 16):
            self.random_sleep(1.5, 2.5)

            # ── Check for success message ──
            for sel in [
                ".applied-msg", ".success-title", ".congrats",
                "div:has-text('Successfully Applied')",
                "div:has-text('Application Sent')",
                "div:has-text('applied successfully')",
                "div:has-text('Thank you for applying')",
            ]:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        self.log("    ✅ Application confirmed!", "SUCCESS")
                        return
                except Exception:
                    pass

            # ══════════════════════════════════════════════════════════
            # PART A: NAUKRI CHATBOT (the right-side slide-in panel)
            # This is the "Type message here..." input box
            # ══════════════════════════════════════════════════════════

            chatbot_filled = self._fill_chatbot_input(page)

            # ══════════════════════════════════════════════════════════
            # PART B: MODAL / DRAWER FORM QUESTIONNAIRES
            # These are traditional form overlays with input fields,
            # radio buttons, dropdowns, and file uploads
            # ══════════════════════════════════════════════════════════

            if not chatbot_filled:
                form_found = self._fill_form_overlay(page, resume_file)
                if not form_found and step > 2:
                    return  # No chatbot and no form → likely done

    def _fill_chatbot_input(self, page) -> bool:
        """
        Handles the Naukri chatbot panel — the one that shows question
        bubbles and has a single "Type message here..." text input.

        Returns True if we found and filled a chatbot input.
        """
        # Find the chatbot input field
        chatbot_input = None
        for sel in [
            "input[placeholder*='Type message']",
            "input[placeholder*='type message']",
            "input[placeholder*='Type a message']",
            "textarea[placeholder*='Type message']",
            "input[placeholder*='message here']",
            "input[placeholder*='your answer']",
            "input[placeholder*='Type here']",
            "input[placeholder*='type here']",
            ".chatbot_input input",
            ".chatbot-input input",
            "div[class*='chatbot'] input[type='text']",
            "div[class*='bot'] input[type='text']",
            "div[class*='Bot'] input[type='text']",
        ]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    chatbot_input = el
                    break
            except Exception:
                pass

        if not chatbot_input:
            return False

        # ── Found chatbot input! Now read the latest question bubble ──
        question_text = ""
        try:
            # Get ALL text from the chatbot container to understand context
            # The chatbot is usually inside a container with class containing
            # 'bot', 'chat', 'drawer', or similar
            for container_sel in [
                "div[class*='botContainer']",
                "div[class*='chatbot']",
                "div[class*='ChatBot']",
                "div[class*='bot-body']",
                "div[class*='chat-container']",
                "div[class*='drawer']",
                "div[class*='Drawer']",
                "div[role='dialog']",
            ]:
                container = page.query_selector(container_sel)
                if container and container.is_visible():
                    question_text = container.text_content() or ""
                    break

            # If we didn't get container text, try getting the last message bubble
            if not question_text:
                bubbles = page.query_selector_all(
                    "div[class*='msg'], div[class*='bubble'], "
                    "div[class*='message'], div[class*='question']"
                )
                if bubbles:
                    question_text = bubbles[-1].text_content() or ""
        except Exception:
            pass

        self.log(f"    💬 Chatbot question: '{question_text[:80].strip()}...'")

        # ── Generate smart answer ──
        answer = self.answer_engine.answer_question(question_text)
        self.log(f"    ✏️ Auto-filling: '{answer}'")

        # ── Type the answer and press Enter ──
        try:
            chatbot_input.click()
            self.random_sleep(0.3, 0.5)
            chatbot_input.fill(answer)
            self.random_sleep(0.3, 0.5)
            chatbot_input.press("Enter")
            self.log(f"    ➡️ Sent answer via Enter key.")
        except Exception as e:
            self.log(f"    ⚠ Chatbot input error: {e}", "WARNING")
            # Try alternative: click a send button
            try:
                send_btn = page.query_selector(
                    "button[class*='send'], button[aria-label*='send'], "
                    "button:has-text('Send'), button[class*='Submit']"
                )
                if send_btn and send_btn.is_visible():
                    send_btn.click()
            except Exception:
                pass

        return True

    def _fill_form_overlay(self, page, resume_file) -> bool:
        """
        Handles traditional form-based questionnaire overlays / modals.
        Returns True if a form overlay was found.
        """
        # Find overlay / modal / drawer
        overlay = None
        for sel in [
            ".botContainer", ".chatbot_container",
            ".questionnaire-container", "div[role='dialog']",
            ".drawer-wrapper", ".modal-content",
            ".chatbot-container", "div[class*='drawer']",
            "div[class*='Drawer']", "div[class*='ques']",
            "div[class*='Dialog']", "section[class*='apply']",
            "div[class*='modal']",
        ]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    overlay = el
                    break
            except Exception:
                pass

        if not overlay:
            return False

        self.log(f"    📋 Found form overlay. Filling fields...")

        # Get all text for context
        overlay_text = ""
        try:
            overlay_text = overlay.text_content().lower() or ""
        except Exception:
            pass

        # ── 1. Fill text/number/textarea inputs ──
        for inp in overlay.query_selector_all(
            "input[type='text'], input[type='number'], input[type='tel'], "
            "input:not([type]), textarea"
        ):
            try:
                if not inp.is_visible():
                    continue
                val = (inp.get_attribute("value") or "").strip()
                if val:
                    continue  # Already filled

                # Build context from field attributes + overlay text
                ctx_parts = [
                    inp.get_attribute("placeholder") or "",
                    inp.get_attribute("name") or "",
                    inp.get_attribute("id") or "",
                    inp.get_attribute("aria-label") or "",
                ]
                try:
                    parent = inp.evaluate_handle("n => n.closest('div, label, fieldset, li')")
                    if parent and parent.as_element():
                        ctx_parts.append(parent.as_element().text_content() or "")
                except Exception:
                    pass
                ctx_parts.append(overlay_text)

                ctx = " ".join(ctx_parts)
                answer = self.answer_engine.answer_question(ctx)
                inp.fill(answer)
                self.log(f"    ✏️ Filled: '{answer}'")
            except Exception:
                pass

        # ── 2. Upload resume ──
        if resume_file and os.path.exists(resume_file):
            for finp in overlay.query_selector_all("input[type='file']"):
                try:
                    finp.set_input_files(resume_file)
                    self.log(f"    📎 Attached: {os.path.basename(resume_file)}")
                except Exception:
                    pass

        # ── 3. Select radio buttons / chips / options ──
        for el in overlay.query_selector_all(
            "label, .chip, .option, span.radio-label, "
            "div.radio-option, button.option, div[class*='chip'], "
            "div[class*='Chip'], span[class*='chip'], "
            "div[class*='option'], li[class*='option']"
        ):
            try:
                txt = (el.text_content() or "").strip()
                if txt and self.answer_engine.pick_radio(txt):
                    el.click()
                    self.log(f"    🔘 Selected: '{txt}'")
                    self.random_sleep(0.3, 0.5)
                    break
            except Exception:
                pass

        # ── 4. Handle dropdowns ──
        for sel_elem in overlay.query_selector_all("select"):
            try:
                if not sel_elem.is_visible():
                    continue
                for opt in sel_elem.query_selector_all("option"):
                    txt = (opt.text_content() or "").strip()
                    if self.answer_engine.pick_radio(txt):
                        val = opt.get_attribute("value")
                        if val:
                            sel_elem.select_option(value=val)
                            self.log(f"    📋 Selected dropdown: '{txt}'")
                            break
            except Exception:
                pass

        # ── 5. Click proceed button ──
        for btn_sel in [
            "button:has-text('Submit')", "button:has-text('Save')",
            "button:has-text('Apply')", "button:has-text('Next')",
            "button:has-text('Continue')", "button:has-text('Proceed')",
            "button:has-text('Save & Apply')",
            "button.submit-btn", "input[type='submit']",
            "button.btn-primary", "button[type='submit']",
        ]:
            try:
                btn = overlay.query_selector(btn_sel)
                if btn and btn.is_visible():
                    name = (btn.text_content() or "Button").strip()
                    self.log(f"    ➡️ Clicking '{name}'...")
                    btn.click()
                    self.random_sleep(1.5, 2.5)
                    return True
            except Exception:
                pass

        return True


if __name__ == "__main__":
    bot = NaukriBot()
    bot.start()
