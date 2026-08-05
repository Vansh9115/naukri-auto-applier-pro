import os
import sys
import json
import time
import random
import subprocess
import urllib.parse
import re
import socket
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from tracker import JobTracker

def load_config(config_path="config.json"):
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_chrome():
    """Find real Google Chrome on this Windows machine."""
    for p in [
        os.path.join(os.environ.get("PROGRAMFILES", ""), r"Google\Chrome\Application\chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), r"Google\Chrome\Application\chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
    ]:
        if os.path.exists(p):
            return p
    return None


def is_port_in_use(port=9222):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def kill_chrome_debug_port(port=9222):
    """Kill any Chrome process listening on the debug port."""
    try:
        subprocess.run(
            f'for /f "tokens=5" %a in (\'netstat -aon ^| findstr :{port} ^| findstr LISTENING\') do taskkill /F /PID %a',
            shell=True, capture_output=True, timeout=5,
        )
    except Exception:
        pass


def cleanup_locks(path):
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        f = os.path.join(path, name)
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass


def launch_real_chrome(url, user_data_dir, port=9222):
    """
    Launch the user's REAL installed Google Chrome with:
    - --remote-debugging-port  (so Playwright can connect via CDP)
    - --user-data-dir          (so login cookies persist)
    - Fully visible on screen

    Returns the subprocess.Popen object or None.
    """
    chrome = find_chrome()
    if not chrome:
        return None

    ud = os.path.abspath(user_data_dir)
    Path(ud).mkdir(parents=True, exist_ok=True)
    cleanup_locks(ud)

    # Kill any old Chrome on this debug port
    if is_port_in_use(port):
        kill_chrome_debug_port(port)
        time.sleep(1)

    try:
        proc = subprocess.Popen([
            chrome,
            f"--user-data-dir={ud}",
            f"--remote-debugging-port={port}",
            "--start-maximized",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-popup-blocking",
            url,
        ])
        return proc
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Smart Answer Engine
# ---------------------------------------------------------------------------

class SmartAnswerEngine:
    """Answers ANY Naukri chatbot / questionnaire prompt automatically."""

    def __init__(self, config):
        self.exp = config.get("experience_years", 4)
        self.curr_ctc = config.get("current_ctc_lpa", 4.0)
        self.exp_ctc = config.get("expected_ctc_lpa", 6.5)
        self.notice_days = config.get("notice_period_days", 15)
        self.locations = config.get("locations", ["Bangalore"])
        self.relocate = config.get("willing_to_relocate", True)
        self.gender = config.get("gender", "Male")
        self.degree = config.get("degree", "B.Com")

    def answer_question(self, question_text: str) -> str:
        q = question_text.lower().strip()

        # YY/MM format
        if "yy/mm" in q or "yy /mm" in q or "years/months" in q:
            return f"{self.exp:02d}/00"

        # CTC (check before experience)
        if any(k in q for k in [
            "current ctc", "present ctc", "current salary", "present salary",
            "current annual", "last drawn", "current compensation", "current package",
        ]):
            return str(self.curr_ctc)
        if any(k in q for k in [
            "expected ctc", "expected salary", "desired ctc", "desired salary",
            "expected annual", "expected compensation", "expected package",
        ]):
            return str(self.exp_ctc)

        # Notice
        if any(k in q for k in ["notice period", "notice", "days to join", "when can you join"]):
            return str(self.notice_days)

        # Location
        if any(k in q for k in ["current location", "current city", "preferred location", "which city"]):
            return self.locations[0] if self.locations else "Bangalore"

        # Relocation
        if any(k in q for k in ["relocat", "willing to relocate"]):
            return "Yes" if self.relocate else "No"

        # Gender
        if "gender" in q:
            return self.gender

        # Education
        if any(k in q for k in ["graduation", "degree", "qualification", "education"]):
            return self.degree

        # Age
        if any(k in q for k in ["age", "date of birth"]):
            return "25"

        # Experience / skills — CATCH ALL
        # Most Naukri chatbot questions ask "How many years in <SKILL>?"
        return str(self.exp)

    def pick_radio(self, option_text: str) -> bool:
        t = option_text.lower().strip()
        exp = self.exp
        if any(s in t for s in [f"{exp} year", f"{exp} yr", f"{exp}+", "3-5", "4-5", "3-6", "4-6", "2-5"]):
            return True
        if any(s in t for s in ["15 day", "immediate", "less than 15", "1 month"]):
            return True
        if self.relocate and t in ("yes", "ready to relocate", "willing to relocate"):
            return True
        if any(loc.lower() in t for loc in self.locations):
            return True
        if t == self.gender.lower():
            return True
        return False


# ---------------------------------------------------------------------------
# Main Bot
# ---------------------------------------------------------------------------

class NaukriBot:
    CDP_PORT = 9222

    def __init__(self, config=None, log_callback=None):
        self.config = config or load_config()
        self.tracker = JobTracker(self.config.get("log_file", "applied_jobs.csv"))
        self.answer_engine = SmartAnswerEngine(self.config)
        self.session_applied = 0
        self.session_skipped = 0
        self.session_failed = 0
        self.session_external = 0
        self.stop_requested = False
        self.log_callback = log_callback
        self.user_data_dir = os.path.abspath(self.config.get("chrome_user_data_dir", "./naukri_chrome_profile"))
        Path(self.user_data_dir).mkdir(parents=True, exist_ok=True)
        self._chrome_proc = None

    def log(self, msg, level="INFO"):
        print(f"[{level}] {msg}")
        if self.log_callback:
            try:
                self.log_callback(msg, level)
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

    # ══════════════════════════════════════════════════════════════════
    # LOGIN — launches REAL Chrome (not Playwright Chromium)
    # ══════════════════════════════════════════════════════════════════

    def ensure_google_login(self):
        """
        Opens the user's REAL Google Chrome to Naukri login page.
        Google OAuth ONLY works in real Chrome (blocks Playwright Chromium).
        The user signs in, and cookies are saved in the persistent profile.
        """
        self.log("🌐 Launching your real Chrome for Google login...", "INFO")
        proc = launch_real_chrome(
            "https://www.naukri.com/nlogin/login",
            self.user_data_dir,
            self.CDP_PORT,
        )
        if not proc:
            self.log("❌ Could not find Chrome.exe on your system!", "ERROR")
            return False

        self.log("✅ Chrome opened! Sign in with Google, then CLOSE Chrome when done.", "SUCCESS")
        self.log("⏳ Waiting for you to finish login and close Chrome...", "INFO")

        # Wait for user to close Chrome
        try:
            proc.wait()
        except Exception:
            pass

        self.log("✅ Login saved! You can now click 'Start Applying'.", "SUCCESS")
        return True

    def ensure_login_manual_only(self):
        """Opens real Chrome for email/password login."""
        self.log("💻 Launching Chrome for email login...", "INFO")
        proc = launch_real_chrome(
            "https://www.naukri.com/nlogin/login",
            self.user_data_dir,
            self.CDP_PORT,
        )
        if not proc:
            self.log("❌ Could not find Chrome.exe!", "ERROR")
            return False

        self.log("✅ Chrome opened! Log in with email/password, then CLOSE Chrome.", "SUCCESS")
        try:
            proc.wait()
        except Exception:
            pass

        self.log("✅ Login saved! Click 'Start Applying' now.", "SUCCESS")
        return True

    # ══════════════════════════════════════════════════════════════════
    # MAIN AUTOMATION — launches Chrome + connects Playwright via CDP
    # ══════════════════════════════════════════════════════════════════

    def start(self):
        self.session_applied = 0
        self.session_skipped = 0
        self.session_failed = 0
        self.session_external = 0
        self.stop_requested = False
        self.log("🚀 Starting session...")

        # Step 1: Launch real Chrome with debugging port
        self.log("Launching Chrome browser...")
        self._chrome_proc = launch_real_chrome(
            "https://www.naukri.com/mnjuser/homepage",
            self.user_data_dir,
            self.CDP_PORT,
        )
        if not self._chrome_proc:
            self.log("❌ Chrome not found! Please install Google Chrome.", "ERROR")
            return

        # Wait for Chrome to start and debugging port to become available
        self.log("Connecting to Chrome browser...")
        for _ in range(15):
            if is_port_in_use(self.CDP_PORT):
                break
            time.sleep(1)
        else:
            self.log("❌ Could not connect to Chrome. Please try again.", "ERROR")
            return

        time.sleep(2)  # Give Chrome a moment to fully initialize

        # Step 2: Connect Playwright to the running Chrome via CDP
        with sync_playwright() as p:
            try:
                browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{self.CDP_PORT}")
            except Exception as e:
                self.log(f"❌ Could not connect Playwright to Chrome: {e}", "ERROR")
                return

            contexts = browser.contexts
            if not contexts:
                self.log("❌ No browser context found.", "ERROR")
                return

            context = contexts[0]
            page = context.pages[0] if context.pages else context.new_page()

            # Navigate to Naukri homepage to verify login
            try:
                page.goto("https://www.naukri.com/mnjuser/homepage", wait_until="domcontentloaded")
                self.random_sleep(2, 3)
            except Exception:
                pass

            if not self._is_logged_in(page, context):
                self.log("⚠️ Not logged in! Please use 'Login with Google' or 'Login with Email' first.", "ERROR")
                self.log("Then close Chrome and click 'Start Applying' again.", "INFO")
                try:
                    browser.close()
                except Exception:
                    pass
                return

            self.log("✅ Logged in! Starting job applications...", "SUCCESS")

            keywords = self.config.get("keywords", ["Operations Management"])
            max_apps = self.config.get("max_applications_per_run", 30)

            for kw in keywords:
                if self.stop_requested or self.session_applied >= max_apps:
                    break
                self.log(f"\n🔍 Searching: '{kw}'")
                self._process_keyword(page, kw)

            self.log(
                f"\n🏁 Done! Applied={self.session_applied} "
                f"Skipped={self.session_skipped} External={self.session_external} "
                f"Failed={self.session_failed}",
                "SUCCESS",
            )

            try:
                browser.close()
            except Exception:
                pass

    def _is_logged_in(self, page, context):
        try:
            url = page.url.lower()
            if any(x in url for x in ["mnjuser/homepage", "mnjuser/profile"]):
                return True
            el = page.query_selector(".nI-gD-profile, a[href*='mnjuser/profile'], .user-name, div[class*='nI-gD']")
            if el and el.is_visible():
                return True
            for c in context.cookies():
                if c.get("name") in ("nauk_at", "nls", "Naukri_User", "n_user"):
                    return True
        except Exception:
            pass
        return False

    # ── Search & scrape ───────────────────────────────────────────────
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

            self.log(f"  Page {pg_num}...")
            try:
                page.wait_for_selector(".srp-jobtuple-wrapper, article.jobTuple, .cust-job-tuple", timeout=8000)
            except Exception:
                self.log("  No jobs found.", "WARNING")
                break

            cards = page.query_selector_all(".srp-jobtuple-wrapper, article.jobTuple, .cust-job-tuple")
            self.log(f"  {len(cards)} job cards found.")

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
                    badge = card.query_selector(".already-applied, span:has-text('Applied')")
                    if badge or self.tracker.is_applied(jid, href, title, company):
                        self.session_skipped += 1
                        continue
                    jobs.append({"id": jid, "title": title, "company": company, "url": href})
                except Exception:
                    continue

            for job in jobs:
                if self.stop_requested or self.session_applied >= self.config.get("max_applications_per_run", 30):
                    break
                self._apply_to_job(page, job)
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

    # ── Apply to single job ───────────────────────────────────────────
    def _apply_to_job(self, parent_page, job):
        self.log(f"👉 {job['title']} @ {job['company']}")
        pg = parent_page.context.new_page()
        try:
            pg.goto(job["url"], wait_until="domcontentloaded")
            self.random_sleep(2, 3)

            apply_btn = pg.query_selector(
                "button#apply-button, button.apply-button, "
                "button:has-text('Apply'), .apply-button-container button"
            )

            if not apply_btn:
                already = pg.query_selector(".already-applied, span:has-text('Already Applied')")
                if already:
                    self.tracker.log_application(job["id"], job["title"], job["company"], "", job["url"], status="ALREADY_APPLIED")
                    self.session_skipped += 1
                else:
                    self.tracker.log_application(job["id"], job["title"], job["company"], "", job["url"], status="SKIPPED", notes="No Apply button")
                    self.session_skipped += 1
                pg.close()
                return

            btn_text = (apply_btn.text_content() or "").strip().lower()
            if any(ext in btn_text for ext in ["company site", "company website", "external", "apply on company"]):
                self.log("  ⏭ External portal. Skipping.", "INFO")
                self.tracker.log_application(job["id"], job["title"], job["company"], "", job["url"], status="EXTERNAL", notes=btn_text)
                self.session_external += 1
                pg.close()
                return

            apply_btn.click()
            self.random_sleep(2, 4)

            # Check external redirect
            if "naukri.com" not in pg.url.lower():
                self.log("  ⏭ Redirected external. Skipping.", "INFO")
                self.tracker.log_application(job["id"], job["title"], job["company"], "", job["url"], status="EXTERNAL", notes="External redirect")
                self.session_external += 1
                pg.close()
                return

            # Solve chatbot + forms
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

    # ══════════════════════════════════════════════════════════════════
    # CHATBOT + FORM SOLVER
    # ══════════════════════════════════════════════════════════════════

    def _solve_chatbot_and_forms(self, page, job):
        resume_file = self.config.get("resume_path", "")

        for step in range(1, 16):
            self.random_sleep(1.5, 2.5)

            # Check success
            for sel in [
                ".applied-msg", ".success-title", ".congrats",
                "div:has-text('Successfully Applied')",
                "div:has-text('Application Sent')",
                "div:has-text('applied successfully')",
            ]:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        self.log("    ✅ Confirmed!", "SUCCESS")
                        return
                except Exception:
                    pass

            # PART A: Chatbot ("Type message here..." input)
            chatbot_handled = self._handle_chatbot(page)

            # PART B: Form overlay
            if not chatbot_handled:
                form_handled = self._handle_form_overlay(page, resume_file)
                if not form_handled and step > 2:
                    return

    def _handle_chatbot(self, page) -> bool:
        """Find the chatbot input, read the question, type answer, press Enter."""
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
            "div[class*='chatbot'] input",
            "div[class*='bot'] input[type='text']",
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

        # Read question context
        question_text = ""
        try:
            for csel in [
                "div[class*='botContainer']", "div[class*='chatbot']",
                "div[class*='ChatBot']", "div[class*='bot-body']",
                "div[class*='chat-container']", "div[class*='drawer']",
                "div[class*='Drawer']", "div[role='dialog']",
            ]:
                container = page.query_selector(csel)
                if container and container.is_visible():
                    question_text = container.text_content() or ""
                    break
            if not question_text:
                bubbles = page.query_selector_all("div[class*='msg'], div[class*='bubble'], div[class*='message']")
                if bubbles:
                    question_text = bubbles[-1].text_content() or ""
        except Exception:
            pass

        self.log(f"    💬 Q: '{question_text[:70].strip()}...'")
        answer = self.answer_engine.answer_question(question_text)
        self.log(f"    ✏️ A: '{answer}'")

        try:
            chatbot_input.click()
            self.random_sleep(0.3, 0.5)
            chatbot_input.fill(answer)
            self.random_sleep(0.3, 0.5)
            chatbot_input.press("Enter")
            self.log("    ➡️ Sent!")
        except Exception as e:
            self.log(f"    ⚠ Input error: {e}", "WARNING")
            try:
                send_btn = page.query_selector("button:has-text('Send'), button[class*='send']")
                if send_btn and send_btn.is_visible():
                    send_btn.click()
            except Exception:
                pass

        return True

    def _handle_form_overlay(self, page, resume_file) -> bool:
        """Handle modal/drawer form questionnaires."""
        overlay = None
        for sel in [
            ".botContainer", ".questionnaire-container", "div[role='dialog']",
            ".drawer-wrapper", ".modal-content", ".chatbot-container",
            "div[class*='drawer']", "div[class*='Drawer']", "div[class*='ques']",
            "div[class*='Dialog']", "section[class*='apply']", "div[class*='modal']",
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

        overlay_text = ""
        try:
            overlay_text = overlay.text_content().lower() or ""
        except Exception:
            pass

        # Fill inputs
        for inp in overlay.query_selector_all(
            "input[type='text'], input[type='number'], input[type='tel'], input:not([type]), textarea"
        ):
            try:
                if not inp.is_visible():
                    continue
                if (inp.get_attribute("value") or "").strip():
                    continue
                ctx = " ".join([
                    inp.get_attribute("placeholder") or "",
                    inp.get_attribute("name") or "",
                    inp.get_attribute("id") or "",
                    inp.get_attribute("aria-label") or "",
                    overlay_text,
                ])
                answer = self.answer_engine.answer_question(ctx)
                inp.fill(answer)
                self.log(f"    ✏️ Filled: '{answer}'")
            except Exception:
                pass

        # Resume
        if resume_file and os.path.exists(resume_file):
            for finp in overlay.query_selector_all("input[type='file']"):
                try:
                    finp.set_input_files(resume_file)
                    self.log(f"    📎 Attached resume")
                except Exception:
                    pass

        # Radio/chips
        for el in overlay.query_selector_all(
            "label, .chip, .option, span.radio-label, div.radio-option, "
            "button.option, div[class*='chip'], div[class*='option']"
        ):
            try:
                txt = (el.text_content() or "").strip()
                if txt and self.answer_engine.pick_radio(txt):
                    el.click()
                    self.log(f"    🔘 Selected: '{txt}'")
                    break
            except Exception:
                pass

        # Dropdowns
        for sel_elem in overlay.query_selector_all("select"):
            try:
                if not sel_elem.is_visible():
                    continue
                for opt in sel_elem.query_selector_all("option"):
                    txt = (opt.text_content() or "").strip()
                    if self.answer_engine.pick_radio(txt):
                        sel_elem.select_option(value=opt.get_attribute("value"))
                        self.log(f"    📋 Dropdown: '{txt}'")
                        break
            except Exception:
                pass

        # Click proceed
        for btn_sel in [
            "button:has-text('Submit')", "button:has-text('Save')",
            "button:has-text('Apply')", "button:has-text('Next')",
            "button:has-text('Continue')", "button:has-text('Proceed')",
            "button:has-text('Save & Apply')", "button.submit-btn",
            "input[type='submit']", "button.btn-primary", "button[type='submit']",
        ]:
            try:
                btn = overlay.query_selector(btn_sel)
                if btn and btn.is_visible():
                    btn.click()
                    self.random_sleep(1.5, 2.5)
                    return True
            except Exception:
                pass

        return True


if __name__ == "__main__":
    bot = NaukriBot()
    bot.start()
