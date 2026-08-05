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

def find_chrome_executable():
    """Find Google Chrome on this Windows machine."""
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None

def open_system_chrome(url="https://www.naukri.com/nlogin/login", user_data_dir="./naukri_user_data"):
    """Launch the real system Chrome browser so it pops up visibly on screen."""
    chrome = find_chrome_executable()
    if not chrome:
        return False
    user_data_path = os.path.abspath(user_data_dir)
    try:
        subprocess.Popen([
            chrome,
            f"--user-data-dir={user_data_path}",
            "--start-maximized",
            "--no-first-run",
            "--no-default-browser-check",
            url,
        ])
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Smart Answer Engine – answers ANY Naukri questionnaire field intelligently
# ---------------------------------------------------------------------------

class SmartAnswerEngine:
    """
    Determines the right answer for any text field / chatbot prompt / radio
    based on keyword matching against the user's profile config.

    Rules:
      - ANY question that mentions "experience" / "years" / "how many" etc. →
        answer with experience_years (e.g. "4").
      - CTC / salary questions → current or expected CTC.
      - Notice period → notice_period_days.
      - Location / city → first preferred location.
      - Relocation → "Yes" / willing.
      - Gender → "Male" (configurable).
      - Graduation / Degree → configurable default.
      - ANY completely unknown field → fill experience_years as a safe numeric
        answer (most Naukri chatbot prompts ask about years of experience in
        some technology / skill, so the years number is almost always correct).
    """

    # ── keyword buckets (order matters: first match wins) ──────────────
    EXPERIENCE_KEYWORDS = [
        "how many year", "years of experience", "experience in",
        "total experience", "work experience", "relevant experience",
        "industry experience", "domain experience", "professional experience",
        "yrs of exp", "years exp", "year of exp", "exp in year",
        "how long have you", "duration of experience", "months of experience",
        "switch configuration", "networking", "firewall",        # skill-specific
        "python", "java", "sql", "excel", "salesforce", "sap",  # tech skills
        "cloud", "aws", "azure", "gcp", "devops", "docker",
        "machine learning", "data analy", "tableau", "power bi",
        "project management", "team lead", "people management",
        "finance", "accounts", "audit", "compliance", "aml",
        "operations", "supply chain", "logistics",
        "how many", "experience", "years", "year", "exp",
    ]

    CTC_CURRENT_KEYWORDS = [
        "current ctc", "present ctc", "current salary", "present salary",
        "current annual", "annual ctc", "last drawn", "current compensation",
        "existing ctc", "current package",
    ]

    CTC_EXPECTED_KEYWORDS = [
        "expected ctc", "expected salary", "desired ctc", "desired salary",
        "expected annual", "expected compensation", "expected package",
    ]

    NOTICE_KEYWORDS = [
        "notice period", "notice", "days to join", "joining time",
        "time to join", "availability", "when can you join",
        "earliest joining", "start date",
    ]

    LOCATION_KEYWORDS = [
        "current location", "location", "city", "current city",
        "preferred location", "where do you",
    ]

    RELOCATE_KEYWORDS = [
        "relocat", "willing to relocate", "ready to relocate",
        "open to relocation", "travel",
    ]

    GENDER_KEYWORDS = ["gender", "sex"]

    GRADUATION_KEYWORDS = [
        "graduation", "degree", "qualification", "education",
        "highest qualification", "bachelor",
    ]

    AGE_KEYWORDS = ["age", "date of birth", "dob"]

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

    def answer_text(self, context_str: str) -> str:
        """Return the best text answer for a given context string."""
        ctx = context_str.lower()

        # Order matters: more specific first, generic last.
        if self._matches(ctx, self.CTC_CURRENT_KEYWORDS):
            return str(self.curr_ctc)
        if self._matches(ctx, self.CTC_EXPECTED_KEYWORDS):
            return str(self.exp_ctc)
        if self._matches(ctx, self.NOTICE_KEYWORDS):
            return str(self.notice_days)
        if self._matches(ctx, self.LOCATION_KEYWORDS):
            return self.locations[0] if self.locations else "Bangalore"
        if self._matches(ctx, self.RELOCATE_KEYWORDS):
            return "Yes" if self.relocate else "No"
        if self._matches(ctx, self.GENDER_KEYWORDS):
            return self.gender
        if self._matches(ctx, self.GRADUATION_KEYWORDS):
            return self.degree
        if self._matches(ctx, self.AGE_KEYWORDS):
            return "25"
        if self._matches(ctx, self.EXPERIENCE_KEYWORDS):
            return str(self.exp)

        # ── Completely unknown field → default to experience years ──
        # Most Naukri chatbot questions are "How many years of exp in <X>?"
        # so a numeric answer is safest.
        return str(self.exp)

    def pick_radio(self, option_text: str) -> bool:
        """Return True if this radio / chip option should be selected."""
        t = option_text.lower()

        # Experience range match
        exp = self.exp
        if any(s in t for s in [
            f"{exp} year", f"{exp} yr", f"{exp}+",
            "3-5", "4-5", "3-6", "4-6", "2-5", "3-7", "4-8",
        ]):
            return True

        # Notice period match
        if any(s in t for s in [
            "15 day", "15 days or less", "immediate", "less than 15",
            "1 month", "within 15",
        ]):
            return True

        # Relocation
        if self.relocate and t.strip() in ["yes", "ready to relocate", "willing to relocate"]:
            return True

        # Location match
        if any(loc.lower() in t for loc in self.locations):
            return True

        # Gender
        if t.strip() == self.gender.lower():
            return True

        return False

    @staticmethod
    def _matches(text, keywords):
        return any(kw in text for kw in keywords)


# ---------------------------------------------------------------------------
# External Redirect Detector
# ---------------------------------------------------------------------------

class ExternalRedirectDetector:
    """Detects whether a job redirects to a company career portal."""

    EXTERNAL_MARKERS_BUTTON = [
        "company site", "company website", "external", "redirect",
        "apply on company", "apply externally",
    ]

    @classmethod
    def is_external_apply(cls, button_text: str) -> bool:
        t = button_text.lower()
        return any(m in t for m in cls.EXTERNAL_MARKERS_BUTTON)

    @classmethod
    def page_redirected_external(cls, page, original_domain="naukri.com") -> bool:
        """Check if clicking Apply opened a new tab pointing outside Naukri."""
        try:
            url = page.url.lower()
            if original_domain not in url and "naukri" not in url:
                return True
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# Main Bot
# ---------------------------------------------------------------------------

class NaukriBot:
    def __init__(self, config=None, log_callback=None):
        self.config = config or load_config()
        self.tracker = JobTracker(self.config.get("log_file", "applied_jobs.csv"))
        self.answer_engine = SmartAnswerEngine(self.config)

        # Session-specific counters (reset to 0 per session)
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

    # ── Logging ───────────────────────────────────────────────────────
    def log(self, msg, level="INFO"):
        print(f"[{level}] {msg}")
        if self.log_callback:
            try:
                self.log_callback(msg, level)
            except Exception:
                pass

    # ── Cleanup ───────────────────────────────────────────────────────
    def _cleanup_stale_locks(self, path):
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
        self.log("Stop requested by user. Finishing current operation...", "WARNING")

    # ── Browser creation ──────────────────────────────────────────────
    def _create_browser_context(self, p, force_visible=True):
        self._cleanup_stale_locks(self.user_data_dir)
        args = [
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
            "--no-sandbox",
            "--disable-notifications",
            "--deny-permission-prompts",
            "--hide-crash-restore-bubble",
            "--disable-session-crashed-bubble",
            "--disable-infobars",
            "--new-window",
            "--window-position=50,50",
            "--window-size=1280,850",
        ]

        def _launch(d):
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=d, headless=False, args=args, no_viewport=True,
            )
            try:
                ctx.grant_permissions(["geolocation", "notifications"])
            except Exception:
                pass
            return ctx

        try:
            return _launch(self.user_data_dir)
        except Exception as e:
            self.log(f"Primary profile warning ({e}). Trying fallback...", "WARNING")
            fb = os.path.abspath("./naukri_user_data_session")
            Path(fb).mkdir(parents=True, exist_ok=True)
            self._cleanup_stale_locks(fb)
            return _launch(fb)

    # ── Main entry point ──────────────────────────────────────────────
    def start(self):
        self.session_applied = 0
        self.session_skipped = 0
        self.session_failed = 0
        self.session_external = 0
        self.stop_requested = False
        self.log("🚀 Starting Naukri Auto-Application Session...")

        with sync_playwright() as p:
            context = self._create_browser_context(p)
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.bring_to_front()
            except Exception:
                pass

            if not self._ensure_login(page, context):
                self.log("Login failed. Stopping session.", "WARNING")
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

    # ── Google login ──────────────────────────────────────────────────
    def ensure_google_login(self):
        """Open Chrome to Naukri login page so user can sign in with Google."""
        self.log("Opening Chrome for Google login to Naukri...")
        # Try system Chrome first (guaranteed visible)
        if open_system_chrome("https://www.naukri.com/nlogin/login", self.user_data_dir):
            self.log("🌐 Chrome opened! Complete Google sign-in in the browser window.", "SUCCESS")
            return

        # Fallback: Playwright visible window
        with sync_playwright() as p:
            ctx = self._create_browser_context(p)
            pg = ctx.pages[0] if ctx.pages else ctx.new_page()
            pg.bring_to_front()
            pg.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded")
            self.log("🌐 Chrome opened! Complete Google sign-in.", "SUCCESS")
            # Keep alive until user closes
            while len(ctx.pages) > 0:
                try:
                    time.sleep(2)
                except Exception:
                    break

    def ensure_login_manual_only(self):
        """Open Chrome to Naukri login page for email/password login."""
        self.log("Opening Chrome for Naukri login...")
        if open_system_chrome("https://www.naukri.com/nlogin/login", self.user_data_dir):
            self.log("🌐 Chrome opened! Log in with your email & password.", "SUCCESS")
            return

        with sync_playwright() as p:
            ctx = self._create_browser_context(p)
            pg = ctx.pages[0] if ctx.pages else ctx.new_page()
            pg.bring_to_front()
            pg.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded")
            self.log("🌐 Chrome opened! Log in with your email & password.", "SUCCESS")
            while len(ctx.pages) > 0:
                try:
                    time.sleep(2)
                except Exception:
                    break

    # ── Login detection ───────────────────────────────────────────────
    def _is_logged_in(self, page, context):
        try:
            url = page.url.lower()
            if "mnjuser/homepage" in url or "mnjuser/profile" in url:
                return True
            el = page.query_selector(
                ".nI-gD-profile, .profile-edit, a[href*='mnjuser/profile'], "
                ".user-name, div[class*='profile']"
            )
            if el and el.is_visible():
                return True
            for c in context.cookies():
                if c.get("name") in ("nls", "Naukri_User", "n_user"):
                    return True
        except Exception:
            pass
        return False

    def _ensure_login(self, page, context):
        self.log("Checking Naukri login session...")
        try:
            page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded")
            self.random_sleep(2, 3)
        except Exception as e:
            self.log(f"Navigation error: {e}", "ERROR")
            return False

        if self._is_logged_in(page, context):
            self.log("✅ Logged in session confirmed!", "SUCCESS")
            return True

        # Auto-fill credentials if available
        email = self.config.get("naukri_email", "").strip()
        pwd = self.config.get("naukri_password", "").strip()
        if email and pwd:
            self.log(f"🔑 Auto-login attempt for '{email}'...")
            try:
                u = page.query_selector("#usernameField, input[placeholder*='Email']")
                if u:
                    u.fill(email)
                    self.random_sleep(0.5, 1)
                p = page.query_selector("#passwordField, input[type='password']")
                if p:
                    p.fill(pwd)
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

        self.log("⏳ Waiting for you to complete login (up to 3 min)...", "INFO")
        for _ in range(60):
            if self.stop_requested:
                return False
            time.sleep(3)
            if self._is_logged_in(page, context):
                self.log("✅ Login detected!", "SUCCESS")
                return True

        self.log("Login timeout.", "ERROR")
        return False

    # ── Search & scrape ───────────────────────────────────────────────
    def _process_keyword(self, page, keyword):
        locs = ",".join(self.config.get("locations", []))
        exp = self.config.get("experience_years", 4)
        kw_slug = keyword.lower().replace(" ", "-")
        url = (
            f"https://www.naukri.com/{kw_slug}-jobs?"
            f"k={urllib.parse.quote(keyword)}&l={urllib.parse.quote(locs)}"
            f"&experience={exp}"
        )
        self.log(f"Loading: {url}")
        try:
            page.goto(url, wait_until="domcontentloaded")
            self.random_sleep(3, 5)
        except Exception as e:
            self.log(f"Search page error: {e}", "ERROR")
            return

        for pg_num in range(1, 6):
            if self.stop_requested:
                break
            if self.session_applied >= self.config.get("max_applications_per_run", 30):
                break

            self.log(f"  Page {pg_num} for '{keyword}'...")
            try:
                page.wait_for_selector(
                    ".srp-jobtuple-wrapper, article.jobTuple, .cust-job-tuple",
                    timeout=8000,
                )
            except Exception:
                self.log(f"  No jobs on page {pg_num}.", "WARNING")
                break

            cards = page.query_selector_all(
                ".srp-jobtuple-wrapper, article.jobTuple, .cust-job-tuple"
            )
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

                    badge = card.query_selector(
                        ".already-applied, span:has-text('Applied'), .applied-badge"
                    )
                    if badge or self.tracker.is_applied(jid, href, title, company):
                        self.session_skipped += 1
                        continue

                    jobs.append({"id": jid, "title": title, "company": company, "url": href})
                except Exception:
                    continue

            for job in jobs:
                if self.stop_requested:
                    break
                if self.session_applied >= self.config.get("max_applications_per_run", 30):
                    break
                self._apply_to_job(page.context, job)
                self.random_sleep()

            # Next page
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

            # Check for external redirect BEFORE clicking
            apply_btn = pg.query_selector(
                "button#apply-button, button.apply-button, "
                "button:has-text('Apply'), "
                "button:has-text('Apply on company site'), "
                ".apply-button-container button"
            )

            if not apply_btn:
                already = pg.query_selector(
                    ".already-applied, span:has-text('Already Applied'), .applied-msg"
                )
                if already:
                    self.log("  ↩ Already applied.", "INFO")
                    self.tracker.log_application(
                        job["id"], job["title"], job["company"], "", job["url"],
                        status="ALREADY_APPLIED",
                    )
                    self.session_skipped += 1
                else:
                    self.log("  ⚠ No Apply button.", "WARNING")
                    self.tracker.log_application(
                        job["id"], job["title"], job["company"], "", job["url"],
                        status="SKIPPED", notes="No Apply button",
                    )
                    self.session_skipped += 1
                pg.close()
                return

            btn_text = (apply_btn.text_content() or "").strip()

            # ── ONLY skip external career portal redirects ──
            if ExternalRedirectDetector.is_external_apply(btn_text):
                self.log(f"  ⏭ External portal: '{btn_text}'. Skipping.", "INFO")
                self.tracker.log_application(
                    job["id"], job["title"], job["company"], "", job["url"],
                    status="EXTERNAL", notes=btn_text,
                )
                self.session_external += 1
                pg.close()
                return

            self.log(f"  Clicking '{btn_text}'...")
            apply_btn.click()
            self.random_sleep(2, 3)

            # After clicking, check if we got redirected to external site
            if ExternalRedirectDetector.page_redirected_external(pg):
                self.log(f"  ⏭ Redirected to external site. Skipping.", "INFO")
                self.tracker.log_application(
                    job["id"], job["title"], job["company"], "", job["url"],
                    status="EXTERNAL", notes="Redirected to external domain",
                )
                self.session_external += 1
                pg.close()
                return

            # Solve any questionnaires / chatbot prompts
            self._solve_questionnaires(pg, job)

            self.log(f"  🎯 Applied to {job['title']} @ {job['company']}", "SUCCESS")
            self.tracker.log_application(
                job["id"], job["title"], job["company"], "", job["url"],
                status="APPLIED",
            )
            self.session_applied += 1

        except Exception as e:
            self.log(f"  ❌ Error: {e}", "ERROR")
            self.tracker.log_application(
                job["id"], job["title"], job["company"], "", job["url"],
                status="FAILED", notes=str(e)[:120],
            )
            self.session_failed += 1
        finally:
            try:
                pg.close()
            except Exception:
                pass

    # ── Questionnaire / Chatbot solver ────────────────────────────────
    def _solve_questionnaires(self, page, job):
        """
        Iteratively solves up to 12 steps of Naukri questionnaire modals,
        chatbot drawers, and slide-in panels.

        NEVER skips a job because of a questionnaire. Fills everything
        automatically using SmartAnswerEngine.
        """
        resume_file = self.config.get("resume_path", "")

        for step in range(1, 13):
            self.random_sleep(1, 2)

            # ── Check for success ──
            success = page.query_selector(
                ".applied-msg, .success-title, "
                "div:has-text('Successfully Applied'), "
                "div:has-text('Application Sent'), "
                "div:has-text('applied successfully'), "
                ".apply-message, .congrats"
            )
            if success:
                try:
                    if success.is_visible():
                        self.log("    ✅ Success confirmation found!", "SUCCESS")
                        return
                except Exception:
                    pass

            # ── Find active overlay / chatbot / drawer ──
            overlay = page.query_selector(
                ".botContainer, .chatbot_container, "
                ".questionnaire-container, div[role='dialog'], "
                ".drawer-wrapper, .modal-content, .chatbot-container, "
                "div[class*='drawer'], div[class*='Drawer'], "
                "div[class*='chatbot'], div[class*='ChatBot'], "
                "div[class*='bot-body'], div[class*='ques'], "
                "div[class*='Dialog'], section[class*='apply']"
            )

            if not overlay:
                if step > 1:
                    return  # Likely done
                time.sleep(1.5)
                continue

            try:
                if not overlay.is_visible():
                    if step > 1:
                        return
                    time.sleep(1)
                    continue
            except Exception:
                continue

            self.log(f"    📋 Step {step}: Solving questionnaire...")

            # ── Collect ALL question / prompt text on the overlay ──
            question_text = ""
            try:
                # Grab every piece of text in the overlay for context
                question_text = overlay.text_content().lower().strip()
            except Exception:
                pass

            # ── 1. Fill ALL text / number / textarea inputs ──
            self._fill_all_inputs(overlay, question_text)

            # ── 2. Upload resume if file input exists ──
            if resume_file and os.path.exists(resume_file):
                for finp in overlay.query_selector_all("input[type='file']"):
                    try:
                        finp.set_input_files(resume_file)
                        self.log(f"    📎 Attached resume: {os.path.basename(resume_file)}")
                    except Exception:
                        pass

            # ── 3. Select best radio / chip / option ──
            self._select_best_options(overlay, question_text)

            # ── 4. Handle dropdowns ──
            self._handle_dropdowns(overlay, question_text)

            # ── 5. Click submit / save / next / continue ──
            self._click_proceed_button(overlay)

    def _fill_all_inputs(self, overlay, question_text):
        """Fill every visible empty text/number/textarea input."""
        selectors = (
            "input[type='text'], input[type='number'], input[type='tel'], "
            "input:not([type]), textarea"
        )
        for inp in overlay.query_selector_all(selectors):
            try:
                if not inp.is_visible():
                    continue
                # Skip already-filled inputs
                val = inp.get_attribute("value") or ""
                if val.strip():
                    continue

                # Build rich context from everything around the input
                ctx_parts = [
                    (inp.get_attribute("placeholder") or ""),
                    (inp.get_attribute("name") or ""),
                    (inp.get_attribute("id") or ""),
                    (inp.get_attribute("aria-label") or ""),
                    question_text,
                ]
                # Try to get label / parent text
                try:
                    parent = inp.evaluate_handle(
                        "n => n.closest('div, label, tr, td, li, fieldset')"
                    )
                    if parent and parent.as_element():
                        ctx_parts.append(parent.as_element().text_content() or "")
                except Exception:
                    pass

                ctx = " ".join(ctx_parts).lower()
                answer = self.answer_engine.answer_text(ctx)
                inp.fill(answer)
                self.log(f"    ✏️ Filled '{answer}' (context: {ctx[:50]}...)")
            except Exception:
                pass

    def _select_best_options(self, overlay, question_text):
        """Click the best matching radio button, chip, or option element."""
        option_els = overlay.query_selector_all(
            "label, .chip, .option, span.radio-label, "
            "div.radio-option, button.option, div[class*='chip'], "
            "div[class*='Chip'], span[class*='chip'], "
            "div[class*='option'], li[class*='option']"
        )
        for el in option_els:
            try:
                txt = el.text_content().strip()
                if not txt:
                    continue
                if self.answer_engine.pick_radio(txt):
                    el.click()
                    self.log(f"    🔘 Selected: '{txt}'")
                    self.random_sleep(0.3, 0.6)
                    break
            except Exception:
                pass

    def _handle_dropdowns(self, overlay, question_text):
        """Handle <select> dropdowns by picking the best option."""
        for sel in overlay.query_selector_all("select"):
            try:
                if not sel.is_visible():
                    continue
                options = sel.query_selector_all("option")
                for opt in options:
                    txt = (opt.text_content() or "").strip()
                    if self.answer_engine.pick_radio(txt):
                        val = opt.get_attribute("value")
                        if val:
                            sel.select_option(value=val)
                            self.log(f"    📋 Selected dropdown: '{txt}'")
                            break
            except Exception:
                pass

    def _click_proceed_button(self, overlay):
        """Click the submit / save / next / continue button."""
        btn_selectors = [
            "button:has-text('Submit')",
            "button:has-text('Save')",
            "button:has-text('Apply')",
            "button:has-text('Next')",
            "button:has-text('Continue')",
            "button:has-text('Save & Apply')",
            "button:has-text('Proceed')",
            "button.submit-btn",
            "input[type='submit']",
            "button.btn-primary",
            "button[type='submit']",
        ]
        for sel in btn_selectors:
            try:
                btn = overlay.query_selector(sel)
                if btn and btn.is_visible():
                    name = (btn.text_content() or "Button").strip()
                    self.log(f"    ➡️ Clicking '{name}'...")
                    btn.click()
                    self.random_sleep(1.5, 2.5)
                    return
            except Exception:
                pass


if __name__ == "__main__":
    bot = NaukriBot()
    bot.start()
