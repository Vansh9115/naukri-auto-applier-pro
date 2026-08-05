import os
import sys
import json
import time
import random
import subprocess
import urllib.parse
import socket
from pathlib import Path
from playwright.sync_api import sync_playwright
from tracker import JobTracker

def load_config(config_path="config.json"):
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_chrome():
    """Find Google Chrome executable on Windows."""
    for p in [
        os.path.join(os.environ.get("PROGRAMFILES", ""), r"Google\Chrome\Application\chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), r"Google\Chrome\Application\chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
    ]:
        if os.path.exists(p):
            return p
    return None


def cleanup_locks(dirpath):
    """Remove Chrome singleton locks so a new instance can start."""
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        fp = os.path.join(dirpath, name)
        if os.path.exists(fp):
            try:
                os.remove(fp)
            except Exception:
                pass


def is_port_open(port):
    """Check if a TCP port is listening on localhost."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            return s.connect_ex(("127.0.0.1", port)) == 0
    except Exception:
        return False


def open_chrome(url, user_data_dir, debug_port=None, log_fn=None):
    """
    Launch REAL Google Chrome with a dedicated profile directory.
    If debug_port is set, enables --remote-debugging-port for CDP.
    Returns the Popen process or None.
    """
    chrome = find_chrome()
    if not chrome:
        if log_fn:
            log_fn("Chrome.exe not found! Please install Google Chrome.", "ERROR")
        return None

    ud = os.path.abspath(user_data_dir)
    Path(ud).mkdir(parents=True, exist_ok=True)
    cleanup_locks(ud)

    args = [
        chrome,
        f"--user-data-dir={ud}",
        "--no-first-run",
        "--no-default-browser-check",
        "--start-maximized",
        "--disable-popup-blocking",
    ]
    if debug_port:
        args.append(f"--remote-debugging-port={debug_port}")
    args.append(url)

    if log_fn:
        log_fn(f"Launching Chrome: {os.path.basename(chrome)}", "INFO")

    try:
        proc = subprocess.Popen(args)
        if log_fn:
            log_fn(f"Chrome started (PID {proc.pid})", "SUCCESS")
        return proc
    except Exception as e:
        if log_fn:
            log_fn(f"Chrome launch failed: {e}", "ERROR")
        return None


# ---------------------------------------------------------------------------
# Smart Answer Engine
# ---------------------------------------------------------------------------

class SmartAnswerEngine:
    """Auto-answers any Naukri chatbot or form question."""

    def __init__(self, config):
        self.exp = config.get("experience_years", 4)
        self.curr_ctc = config.get("current_ctc_lpa", 4.0)
        self.exp_ctc = config.get("expected_ctc_lpa", 6.5)
        self.notice_days = config.get("notice_period_days", 15)
        self.locations = config.get("locations", ["Bangalore"])
        self.relocate = config.get("willing_to_relocate", True)
        self.gender = config.get("gender", "Male")
        self.degree = config.get("degree", "B.Com")

    def answer(self, question: str) -> str:
        q = question.lower()
        if "yy/mm" in q or "years/months" in q:
            return f"{self.exp:02d}/00"
        if any(k in q for k in ["current ctc", "present ctc", "current salary", "present salary", "current package", "last drawn"]):
            return str(self.curr_ctc)
        if any(k in q for k in ["expected ctc", "expected salary", "desired ctc", "desired salary", "expected package"]):
            return str(self.exp_ctc)
        if any(k in q for k in ["notice period", "notice", "days to join", "when can you join"]):
            return str(self.notice_days)
        if any(k in q for k in ["current location", "current city", "preferred location", "which city"]):
            return self.locations[0] if self.locations else "Bangalore"
        if "relocat" in q:
            return "Yes" if self.relocate else "No"
        if "gender" in q:
            return self.gender
        if any(k in q for k in ["graduation", "degree", "qualification", "education"]):
            return self.degree
        if "age" in q or "date of birth" in q:
            return "25"
        # Default: experience years (most chatbot questions ask about skill experience)
        return str(self.exp)

    def should_select(self, option_text: str) -> bool:
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
        return False


# ---------------------------------------------------------------------------
# Main Bot
# ---------------------------------------------------------------------------

PROFILE_DIR = "./naukri_login_profile"
CDP_PORT = 9222


class NaukriBot:
    def __init__(self, config=None, log_callback=None):
        self.config = config or load_config()
        self.tracker = JobTracker(self.config.get("log_file", "applied_jobs.csv"))
        self.engine = SmartAnswerEngine(self.config)
        self.session_applied = 0
        self.session_skipped = 0
        self.session_failed = 0
        self.session_external = 0
        self.stop_requested = False
        self.log_callback = log_callback

    def log(self, msg, level="INFO"):
        print(f"[{level}] {msg}")
        if self.log_callback:
            try:
                self.log_callback(msg, level)
            except Exception:
                pass

    def random_sleep(self, lo=None, hi=None):
        if lo is None:
            d = self.config.get("delay_between_jobs_seconds", [3, 6])
            lo, hi = d[0], d[1]
        time.sleep(random.uniform(lo, hi))

    def stop(self):
        self.stop_requested = True
        self.log("Stop requested.", "WARNING")

    # ══════════════════════════════════════════════════════════════════
    # LOGIN — Opens real Chrome so user can log in with Google/Email
    # ══════════════════════════════════════════════════════════════════

    def ensure_google_login(self):
        """Open real Chrome to Naukri login. User signs in with Google."""
        self.log("🌐 Opening your Chrome browser for Google login...", "INFO")
        proc = open_chrome(
            "https://www.naukri.com/nlogin/login",
            PROFILE_DIR,
            log_fn=self.log,
        )
        if not proc:
            self.log("❌ Failed to open Chrome! Is Google Chrome installed?", "ERROR")
            return
        self.log("✅ Chrome opened! Sign in with Google on the Naukri page.", "SUCCESS")
        self.log("📌 After signing in, CLOSE the Chrome window to save your session.", "INFO")
        try:
            proc.wait()  # Block until user closes Chrome
        except Exception:
            pass
        self.log("✅ Login session saved! You can now click 'Start Applying'.", "SUCCESS")

    def ensure_login_manual_only(self):
        """Open real Chrome for email/password login."""
        self.log("💻 Opening Chrome for email login...", "INFO")
        proc = open_chrome(
            "https://www.naukri.com/nlogin/login",
            PROFILE_DIR,
            log_fn=self.log,
        )
        if not proc:
            self.log("❌ Failed to open Chrome!", "ERROR")
            return
        self.log("✅ Chrome opened! Log in with your email & password.", "SUCCESS")
        self.log("📌 After logging in, CLOSE Chrome to save your session.", "INFO")
        try:
            proc.wait()
        except Exception:
            pass
        self.log("✅ Login saved! Click 'Start Applying'.", "SUCCESS")

    # ══════════════════════════════════════════════════════════════════
    # AUTOMATION — Launches Chrome with CDP and connects Playwright
    # ══════════════════════════════════════════════════════════════════

    def start(self):
        self.session_applied = 0
        self.session_skipped = 0
        self.session_failed = 0
        self.session_external = 0
        self.stop_requested = False
        self.log("🚀 Starting auto-application session...")

        # Launch Chrome with remote debugging
        self.log("Launching Chrome with automation port...")
        proc = open_chrome(
            "https://www.naukri.com/mnjuser/homepage",
            PROFILE_DIR,
            debug_port=CDP_PORT,
            log_fn=self.log,
        )
        if not proc:
            self.log("❌ Cannot start: Chrome not found.", "ERROR")
            return

        # Wait for debugging port to become available
        self.log("Waiting for Chrome to be ready...")
        for i in range(20):
            if is_port_open(CDP_PORT):
                break
            time.sleep(1)
        else:
            self.log("❌ Chrome debugging port not available. Try closing Chrome and retry.", "ERROR")
            return

        time.sleep(2)
        self.log("Connecting Playwright to Chrome...")

        with sync_playwright() as p:
            try:
                browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
            except Exception as e:
                self.log(f"❌ Cannot connect to Chrome: {e}", "ERROR")
                self.log("💡 Try: Close all Chrome windows, then click Start again.", "INFO")
                return

            contexts = browser.contexts
            if not contexts:
                self.log("❌ No browser context found.", "ERROR")
                return

            context = contexts[0]
            page = context.pages[0] if context.pages else context.new_page()

            # Check login
            try:
                page.goto("https://www.naukri.com/mnjuser/homepage", wait_until="domcontentloaded")
                self.random_sleep(2, 3)
            except Exception:
                pass

            if not self._is_logged_in(page, context):
                self.log("⚠️ Not logged in! Use 'Login with Google' first, then try again.", "ERROR")
                try:
                    browser.close()
                except Exception:
                    pass
                return

            self.log("✅ Logged in! Searching for jobs...", "SUCCESS")

            keywords = self.config.get("keywords", ["Operations Management"])
            max_apps = self.config.get("max_applications_per_run", 30)

            for kw in keywords:
                if self.stop_requested or self.session_applied >= max_apps:
                    break
                self.log(f"\n🔍 Searching: '{kw}'")
                self._search_and_apply(page, kw)

            self.log(
                f"\n🏁 Session complete! Applied={self.session_applied} "
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
            el = page.query_selector(".nI-gD-profile, a[href*='mnjuser/profile'], .user-name")
            if el and el.is_visible():
                return True
            for c in context.cookies():
                if c.get("name") in ("nauk_at", "nls", "n_user"):
                    return True
        except Exception:
            pass
        return False

    def _search_and_apply(self, page, keyword):
        locs = ",".join(self.config.get("locations", []))
        exp = self.config.get("experience_years", 4)
        url = (
            f"https://www.naukri.com/{keyword.lower().replace(' ', '-')}-jobs?"
            f"k={urllib.parse.quote(keyword)}&l={urllib.parse.quote(locs)}&experience={exp}"
        )
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
                break

            cards = page.query_selector_all(".srp-jobtuple-wrapper, article.jobTuple, .cust-job-tuple")
            self.log(f"  {len(cards)} jobs found.")

            jobs = []
            for card in cards:
                try:
                    a = card.query_selector("a.title, a.title.ellipsis")
                    if not a:
                        continue
                    href = a.get_attribute("href")
                    title = a.text_content().strip()
                    ce = card.query_selector("a.subTitle, span.comp-name")
                    company = ce.text_content().strip() if ce else "Unknown"
                    jid = card.get_attribute("data-job-id") or href
                    if self.tracker.is_applied(jid, href, title, company):
                        self.session_skipped += 1
                        continue
                    jobs.append({"id": jid, "title": title, "company": company, "url": href})
                except Exception:
                    continue

            for job in jobs:
                if self.stop_requested or self.session_applied >= self.config.get("max_applications_per_run", 30):
                    break
                self._apply_job(page, job)
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

    def _apply_job(self, parent_page, job):
        self.log(f"👉 {job['title']} @ {job['company']}")
        pg = parent_page.context.new_page()
        try:
            pg.goto(job["url"], wait_until="domcontentloaded")
            self.random_sleep(2, 3)

            btn = pg.query_selector("button#apply-button, button.apply-button, button:has-text('Apply'), .apply-button-container button")
            if not btn:
                al = pg.query_selector(".already-applied, span:has-text('Already Applied')")
                self.tracker.log_application(job["id"], job["title"], job["company"], "", job["url"],
                    status="ALREADY_APPLIED" if al else "SKIPPED", notes="" if al else "No button")
                self.session_skipped += 1
                pg.close()
                return

            txt = (btn.text_content() or "").lower()
            if any(x in txt for x in ["company site", "company website", "external", "apply on company"]):
                self.log("  ⏭ External portal. Skip.", "INFO")
                self.tracker.log_application(job["id"], job["title"], job["company"], "", job["url"], status="EXTERNAL", notes=txt)
                self.session_external += 1
                pg.close()
                return

            btn.click()
            self.random_sleep(2, 4)

            if "naukri.com" not in pg.url.lower():
                self.log("  ⏭ External redirect. Skip.", "INFO")
                self.tracker.log_application(job["id"], job["title"], job["company"], "", job["url"], status="EXTERNAL")
                self.session_external += 1
                pg.close()
                return

            self._solve_all(pg)
            self.log(f"  🎯 Applied: {job['title']}", "SUCCESS")
            self.tracker.log_application(job["id"], job["title"], job["company"], "", job["url"], status="APPLIED")
            self.session_applied += 1

        except Exception as e:
            self.log(f"  ❌ {e}", "ERROR")
            self.tracker.log_application(job["id"], job["title"], job["company"], "", job["url"], status="FAILED", notes=str(e)[:100])
            self.session_failed += 1
        finally:
            try:
                pg.close()
            except Exception:
                pass

    # ══════════════════════════════════════════════════════════════════
    # QUESTIONNAIRE / CHATBOT SOLVER
    # ══════════════════════════════════════════════════════════════════

    def _solve_all(self, page):
        """Solve chatbot prompts + form overlays. Up to 15 rounds."""
        resume = self.config.get("resume_path", "")
        for step in range(1, 16):
            self.random_sleep(1, 2)

            # Check success
            for sel in [".applied-msg", ".success-title", ".congrats",
                        "div:has-text('Successfully Applied')", "div:has-text('Application Sent')"]:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        return
                except Exception:
                    pass

            # Try chatbot first, then form overlay
            if not self._chatbot(page):
                if not self._form(page, resume):
                    if step > 2:
                        return

    def _chatbot(self, page) -> bool:
        """Handle the chatbot 'Type message here...' input."""
        inp = None
        for sel in [
            "input[placeholder*='Type message']", "input[placeholder*='type message']",
            "input[placeholder*='Type a message']", "input[placeholder*='message here']",
            "input[placeholder*='Type here']", "input[placeholder*='type here']",
            "textarea[placeholder*='Type message']", "textarea[placeholder*='type message']",
            ".chatbot_input input", ".chatbot-input input",
            "div[class*='chatbot'] input", "div[class*='bot'] input[type='text']",
        ]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    inp = el
                    break
            except Exception:
                pass

        if not inp:
            return False

        # Read question
        qtext = ""
        try:
            for cs in ["div[class*='botContainer']", "div[class*='chatbot']", "div[class*='bot-body']",
                        "div[class*='drawer']", "div[class*='Drawer']", "div[role='dialog']"]:
                c = page.query_selector(cs)
                if c and c.is_visible():
                    qtext = c.text_content() or ""
                    break
        except Exception:
            pass

        self.log(f"    💬 Q: {qtext[:60].strip()}...")
        answer = self.engine.answer(qtext)
        self.log(f"    ✏️ A: {answer}")

        try:
            inp.click()
            time.sleep(0.3)
            inp.fill(answer)
            time.sleep(0.3)
            inp.press("Enter")
        except Exception:
            try:
                sb = page.query_selector("button:has-text('Send'), button[class*='send']")
                if sb and sb.is_visible():
                    sb.click()
            except Exception:
                pass

        return True

    def _form(self, page, resume) -> bool:
        """Handle form-based questionnaire overlays."""
        overlay = None
        for sel in [".botContainer", ".questionnaire-container", "div[role='dialog']",
                    ".drawer-wrapper", ".modal-content", "div[class*='drawer']",
                    "div[class*='Drawer']", "div[class*='ques']", "div[class*='modal']"]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    overlay = el
                    break
            except Exception:
                pass

        if not overlay:
            return False

        ctx = ""
        try:
            ctx = (overlay.text_content() or "").lower()
        except Exception:
            pass

        # Fill inputs
        for inp in overlay.query_selector_all("input[type='text'], input[type='number'], input[type='tel'], input:not([type]), textarea"):
            try:
                if not inp.is_visible() or (inp.get_attribute("value") or "").strip():
                    continue
                fctx = " ".join(filter(None, [inp.get_attribute("placeholder"), inp.get_attribute("name"),
                                               inp.get_attribute("id"), inp.get_attribute("aria-label"), ctx]))
                inp.fill(self.engine.answer(fctx))
            except Exception:
                pass

        # Resume upload
        if resume and os.path.exists(resume):
            for fi in overlay.query_selector_all("input[type='file']"):
                try:
                    fi.set_input_files(resume)
                except Exception:
                    pass

        # Radio/chips
        for el in overlay.query_selector_all("label, .chip, .option, div[class*='chip'], div[class*='option']"):
            try:
                t = (el.text_content() or "").strip()
                if t and self.engine.should_select(t):
                    el.click()
                    break
            except Exception:
                pass

        # Dropdowns
        for se in overlay.query_selector_all("select"):
            try:
                if not se.is_visible():
                    continue
                for opt in se.query_selector_all("option"):
                    t = (opt.text_content() or "").strip()
                    if self.engine.should_select(t):
                        se.select_option(value=opt.get_attribute("value"))
                        break
            except Exception:
                pass

        # Submit
        for bs in ["button:has-text('Submit')", "button:has-text('Save')", "button:has-text('Apply')",
                    "button:has-text('Next')", "button:has-text('Continue')", "button:has-text('Proceed')",
                    "button.submit-btn", "button.btn-primary", "button[type='submit']", "input[type='submit']"]:
            try:
                b = overlay.query_selector(bs)
                if b and b.is_visible():
                    b.click()
                    self.random_sleep(1.5, 2.5)
                    return True
            except Exception:
                pass

        return True


if __name__ == "__main__":
    bot = NaukriBot()
    bot.start()
