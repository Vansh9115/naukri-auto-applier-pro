import os
import sys
import json
import time
import random
import urllib.parse
from pathlib import Path
from playwright.sync_api import sync_playwright
from tracker import JobTracker

def load_config(config_path="config.json"):
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def cleanup_locks(dirpath):
    """Remove Playwright/Chrome lock files if present."""
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        fp = os.path.join(dirpath, name)
        if os.path.exists(fp):
            try:
                os.remove(fp)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Smart Answer Engine — Intelligent questionnaire and chatbot solver
# ---------------------------------------------------------------------------

class SmartAnswerEngine:
    """Answers any Naukri chatbot or questionnaire prompt automatically."""

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
        q = question.lower().strip()
        if "yy/mm" in q or "years/months" in q or "yy / mm" in q:
            return f"{self.exp:02d}/00"
        if any(k in q for k in ["current ctc", "present ctc", "current salary", "present salary", "current package", "last drawn"]):
            return str(self.curr_ctc)
        if any(k in q for k in ["expected ctc", "expected salary", "desired ctc", "desired salary", "expected package"]):
            return str(self.exp_ctc)
        if any(k in q for k in ["notice period", "notice", "days to join", "when can you join", "joining time"]):
            return str(self.notice_days)
        if any(k in q for k in ["current location", "current city", "preferred location", "which city"]):
            return self.locations[0] if self.locations else "Bangalore"
        if "relocat" in q:
            return "Yes" if self.relocate else "No"
        if "gender" in q or "sex" in q:
            return self.gender
        if any(k in q for k in ["graduation", "degree", "qualification", "education"]):
            return self.degree
        if "age" in q or "date of birth" in q:
            return "25"
        # Default: experience years (most chatbot prompts ask for years of experience in a technology)
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
# Main Bot Engine using Playwright + Real Installed Chrome
# ---------------------------------------------------------------------------

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
        self.user_data_dir = os.path.abspath(self.config.get("chrome_user_data_dir", "./naukri_chrome_profile"))
        Path(self.user_data_dir).mkdir(parents=True, exist_ok=True)

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
        self.log("Stop requested by user.", "WARNING")

    def _launch_browser_context(self, p):
        """Launch Playwright using real installed Google Chrome (channel='chrome')."""
        cleanup_locks(self.user_data_dir)
        args = [
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
            "--no-sandbox",
            "--disable-notifications",
            "--deny-permission-prompts",
            "--hide-crash-restore-bubble",
            "--disable-session-crashed-bubble",
            "--disable-infobars",
        ]
        
        # Try launching real Chrome first via channel="chrome"
        try:
            return p.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                channel="chrome",
                headless=False,
                args=args,
                no_viewport=True
            )
        except Exception as e:
            self.log(f"Channel 'chrome' note ({e}). Falling back to bundled Chromium...", "WARNING")
            return p.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=False,
                args=args,
                no_viewport=True
            )

    # ══════════════════════════════════════════════════════════════════
    # LOGIN FLOWS
    # ══════════════════════════════════════════════════════════════════

    def ensure_google_login(self):
        """Opens real Chrome so user can click 'Login with Google' on Naukri."""
        self.log("🌐 Opening Chrome window for Google login...", "INFO")
        with sync_playwright() as p:
            ctx = self._launch_browser_context(p)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.bring_to_front()
            except Exception:
                pass
            
            page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded")
            self.log("✅ Chrome window opened! Please sign in to Naukri using Google or Email.", "SUCCESS")
            self.log("📌 Keep the Chrome window open or close it when done. Session is saved automatically.", "INFO")

            # Wait until user closes the window or logs in
            start_time = time.time()
            while time.time() - start_time < 300: # 5 mins max wait
                if self.stop_requested:
                    break
                try:
                    if len(ctx.pages) == 0:
                        break
                    if self._is_logged_in(page, ctx):
                        self.log("✅ Login detected! Session successfully saved.", "SUCCESS")
                        time.sleep(2)
                        break
                except Exception:
                    break
                time.sleep(2)

            try:
                ctx.close()
            except Exception:
                pass

    def ensure_login_manual_only(self):
        """Opens Chrome for email/password login."""
        self.log("💻 Opening Chrome for email login...", "INFO")
        with sync_playwright() as p:
            ctx = self._launch_browser_context(p)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.bring_to_front()
            except Exception:
                pass

            page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded")
            self.log("✅ Chrome window opened! Please log into Naukri.", "SUCCESS")

            start_time = time.time()
            while time.time() - start_time < 300:
                if self.stop_requested:
                    break
                try:
                    if len(ctx.pages) == 0:
                        break
                    if self._is_logged_in(page, ctx):
                        self.log("✅ Login confirmed! Session saved.", "SUCCESS")
                        time.sleep(2)
                        break
                except Exception:
                    break
                time.sleep(2)

            try:
                ctx.close()
            except Exception:
                pass

    # ══════════════════════════════════════════════════════════════════
    # MAIN APPLICATION ENGINE
    # ══════════════════════════════════════════════════════════════════

    def start(self):
        self.session_applied = 0
        self.session_skipped = 0
        self.session_failed = 0
        self.session_external = 0
        self.stop_requested = False
        self.log("🚀 Starting Naukri Auto-Application Session...")

        with sync_playwright() as p:
            ctx = self._launch_browser_context(p)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.bring_to_front()
            except Exception:
                pass

            self.log("Checking Naukri login session...")
            try:
                page.goto("https://www.naukri.com/mnjuser/homepage", wait_until="domcontentloaded")
                self.random_sleep(2, 3)
            except Exception as e:
                self.log(f"Navigation note: {e}", "WARNING")

            if not self._is_logged_in(page, ctx):
                self.log("⚠️ Not logged in! Opening login page in Chrome...", "WARNING")
                page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded")
                self.log("👉 Please complete sign in in the opened Chrome window. Waiting up to 3 minutes...", "INFO")
                
                logged_in = False
                for _ in range(60):
                    if self.stop_requested:
                        break
                    time.sleep(3)
                    if self._is_logged_in(page, ctx):
                        logged_in = True
                        break

                if not logged_in:
                    self.log("❌ Login timeout or not logged in. Please click 'Login with Google' first.", "ERROR")
                    try:
                        ctx.close()
                    except Exception:
                        pass
                    return

            self.log("✅ Login confirmed! Searching jobs...", "SUCCESS")

            keywords = self.config.get("keywords", ["Operations Management"])
            max_apps = self.config.get("max_applications_per_run", 30)

            for kw in keywords:
                if self.stop_requested or self.session_applied >= max_apps:
                    break
                self.log(f"\n🔍 Searching for keyword: '{kw}'")
                self._search_and_apply(page, kw)

            self.log(
                f"\n🏁 Session Complete! Applied: {self.session_applied} | "
                f"Skipped: {self.session_skipped} | External Redirects: {self.session_external} | "
                f"Failed: {self.session_failed}",
                "SUCCESS",
            )
            try:
                ctx.close()
            except Exception:
                pass

    def _is_logged_in(self, page, context):
        try:
            url = page.url.lower()
            if any(x in url for x in ["mnjuser/homepage", "mnjuser/profile", "naukri.com/mnjuser"]):
                return True
            el = page.query_selector(".nI-gD-profile, a[href*='mnjuser/profile'], .user-name, div[class*='profile']")
            if el and el.is_visible():
                return True
            for c in context.cookies():
                if c.get("name") in ("nauk_at", "nls", "n_user", "Naukri_User"):
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
        self.log(f"Loading search URL: {url}")
        try:
            page.goto(url, wait_until="domcontentloaded")
            self.random_sleep(3, 5)
        except Exception as e:
            self.log(f"Search loading error: {e}", "ERROR")
            return

        for pg_num in range(1, 6):
            if self.stop_requested or self.session_applied >= self.config.get("max_applications_per_run", 30):
                break

            self.log(f"Processing Page {pg_num} for '{keyword}'...")
            try:
                page.wait_for_selector(".srp-jobtuple-wrapper, article.jobTuple, .cust-job-tuple", timeout=8000)
            except Exception:
                self.log(f"No job cards found on page {pg_num}.", "WARNING")
                break

            cards = page.query_selector_all(".srp-jobtuple-wrapper, article.jobTuple, .cust-job-tuple")
            self.log(f"Found {len(cards)} job cards on page {pg_num}.")

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
                self._apply_job(page.context, job)
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

    def _apply_job(self, context, job):
        self.log(f"👉 Opening Job: {job['title']} @ {job['company']}")
        pg = context.new_page()
        try:
            pg.goto(job["url"], wait_until="domcontentloaded")
            self.random_sleep(2, 3)

            btn = pg.query_selector("button#apply-button, button.apply-button, button:has-text('Apply'), .apply-button-container button")
            if not btn:
                al = pg.query_selector(".already-applied, span:has-text('Already Applied')")
                if al:
                    self.tracker.log_application(job["id"], job["title"], job["company"], "", job["url"], status="ALREADY_APPLIED")
                else:
                    self.tracker.log_application(job["id"], job["title"], job["company"], "", job["url"], status="SKIPPED", notes="No Apply button")
                self.session_skipped += 1
                pg.close()
                return

            txt = (btn.text_content() or "").lower()
            if any(x in txt for x in ["company site", "company website", "external", "apply on company"]):
                self.log("  ⏭ Skipping company portal redirect.", "INFO")
                self.tracker.log_application(job["id"], job["title"], job["company"], "", job["url"], status="EXTERNAL", notes=txt)
                self.session_external += 1
                pg.close()
                return

            self.log("  Clicking Apply...")
            btn.click()
            self.random_sleep(2, 4)

            if "naukri.com" not in pg.url.lower():
                self.log("  ⏭ External portal redirect detected. Skipping.", "INFO")
                self.tracker.log_application(job["id"], job["title"], job["company"], "", job["url"], status="EXTERNAL")
                self.session_external += 1
                pg.close()
                return

            self._solve_questionnaires_and_chatbot(pg)
            self.log(f"  🎯 SUCCESS: Applied to {job['title']} @ {job['company']}", "SUCCESS")
            self.tracker.log_application(job["id"], job["title"], job["company"], "", job["url"], status="APPLIED")
            self.session_applied += 1

        except Exception as e:
            self.log(f"  ❌ Application Error: {e}", "ERROR")
            self.tracker.log_application(job["id"], job["title"], job["company"], "", job["url"], status="FAILED", notes=str(e)[:100])
            self.session_failed += 1
        finally:
            try:
                pg.close()
            except Exception:
                pass

    # ══════════════════════════════════════════════════════════════════
    # CHATBOT + QUESTIONNAIRE SOLVER
    # ══════════════════════════════════════════════════════════════════

    def _solve_questionnaires_and_chatbot(self, page):
        """Solves chatbot prompts & questionnaire forms iteratively."""
        resume = self.config.get("resume_path", "")
        for step in range(1, 16):
            self.random_sleep(1.5, 2.5)

            # Check for application success
            for sel in [".applied-msg", ".success-title", ".congrats",
                        "div:has-text('Successfully Applied')", "div:has-text('Application Sent')"]:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        self.log("    ✅ Application confirmation verified!", "SUCCESS")
                        return
                except Exception:
                    pass

            # 1. Chatbot input ("Type message here...")
            if self._fill_chatbot(page):
                continue

            # 2. Form overlay modal
            if not self._fill_form_overlay(page, resume):
                if step > 2:
                    return

    def _fill_chatbot(self, page) -> bool:
        """Find chatbot text input, extract question bubble, type answer, press Enter."""
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

        self.log(f"    💬 Chatbot Question: '{qtext[:60].strip()}...'")
        answer = self.engine.answer(qtext)
        self.log(f"    ✏️ Auto-filled Answer: '{answer}'")

        try:
            inp.click()
            time.sleep(0.3)
            inp.fill(answer)
            time.sleep(0.3)
            inp.press("Enter")
            self.log("    ➡️ Submitted via Enter key.")
        except Exception:
            try:
                sb = page.query_selector("button:has-text('Send'), button[class*='send']")
                if sb and sb.is_visible():
                    sb.click()
            except Exception:
                pass

        return True

    def _fill_form_overlay(self, page, resume) -> bool:
        """Handle modal overlay forms."""
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

        # Text inputs
        for inp in overlay.query_selector_all("input[type='text'], input[type='number'], input[type='tel'], input:not([type]), textarea"):
            try:
                if not inp.is_visible() or (inp.get_attribute("value") or "").strip():
                    continue
                fctx = " ".join(filter(None, [inp.get_attribute("placeholder"), inp.get_attribute("name"),
                                               inp.get_attribute("id"), inp.get_attribute("aria-label"), ctx]))
                ans = self.engine.answer(fctx)
                inp.fill(ans)
                self.log(f"    ✏️ Filled Form Input: '{ans}'")
            except Exception:
                pass

        # Resume upload
        if resume and os.path.exists(resume):
            for fi in overlay.query_selector_all("input[type='file']"):
                try:
                    fi.set_input_files(resume)
                    self.log(f"    📎 Attached Resume: {os.path.basename(resume)}")
                except Exception:
                    pass

        # Radio & options
        for el in overlay.query_selector_all("label, .chip, .option, div[class*='chip'], div[class*='option']"):
            try:
                t = (el.text_content() or "").strip()
                if t and self.engine.should_select(t):
                    el.click()
                    self.log(f"    🔘 Selected Option: '{t}'")
                    break
            except Exception:
                pass

        # Select dropdowns
        for se in overlay.query_selector_all("select"):
            try:
                if not se.is_visible():
                    continue
                for opt in se.query_selector_all("option"):
                    t = (opt.text_content() or "").strip()
                    if self.engine.should_select(t):
                        se.select_option(value=opt.get_attribute("value"))
                        self.log(f"    📋 Selected Dropdown Option: '{t}'")
                        break
            except Exception:
                pass

        # Save/Submit/Next button
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
