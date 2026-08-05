import os
import sys
import json
import time
import random
import urllib.parse
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from tracker import JobTracker

def load_config(config_path="config.json"):
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

class NaukriBot:
    def __init__(self, config=None, log_callback=None):
        self.config = config or load_config()
        self.tracker = JobTracker(self.config.get("log_file", "applied_jobs.csv"))
        self.applied_count = 0
        self.skipped_count = 0
        self.failed_count = 0
        self.stop_requested = False
        self.log_callback = log_callback
        self.user_data_dir = os.path.abspath(self.config.get("chrome_user_data_dir", "./naukri_user_data"))
        Path(self.user_data_dir).mkdir(parents=True, exist_ok=True)

    def log(self, msg, level="INFO"):
        prefix = f"[{level}] "
        full_msg = f"{prefix}{msg}"
        print(full_msg)
        if self.log_callback:
            try:
                self.log_callback(msg, level)
            except Exception:
                pass

    def _cleanup_stale_locks(self, user_data_path):
        """ Cleans up Chromium lock files if left by crashed instances """
        for lock_name in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
            lock_file = os.path.join(user_data_path, lock_name)
            if os.path.exists(lock_file):
                try:
                    os.remove(lock_file)
                except Exception:
                    pass

    def random_sleep(self, min_s=None, max_s=None):
        if min_s is None or max_s is None:
            delay_range = self.config.get("delay_between_jobs_seconds", [3, 6])
            min_s, max_s = delay_range[0], delay_range[1]
        t = random.uniform(min_s, max_s)
        time.sleep(t)

    def stop(self):
        self.stop_requested = True
        self.log("Stop requested by user. Finishing current operation...", "WARNING")

    def _create_browser_context(self, p, force_visible=False):
        """ Creates browser context with automatic lock recovery & popup suppression """
        self._cleanup_stale_locks(self.user_data_dir)
        headless_mode = False if force_visible else self.config.get("headless", False)
        
        args = [
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
            "--no-sandbox",
            "--disable-notifications",
            "--deny-permission-prompts",
            "--hide-crash-restore-bubble",
            "--disable-session-crashed-bubble",
            "--disable-infobars"
        ]

        def _launch(dir_path):
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=dir_path,
                headless=headless_mode,
                args=args,
                no_viewport=True
            )
            try:
                ctx.grant_permissions(['geolocation', 'notifications'])
            except Exception:
                pass
            return ctx

        try:
            return _launch(self.user_data_dir)
        except Exception as e:
            self.log(f"Primary profile launch warning ({e}). Attempting session recovery...", "WARNING")
            fallback_dir = os.path.abspath("./naukri_user_data_session")
            Path(fallback_dir).mkdir(parents=True, exist_ok=True)
            self._cleanup_stale_locks(fallback_dir)
            return _launch(fallback_dir)

    def start(self):
        self.stop_requested = False
        self.log("🚀 Starting Naukri Auto-Application Assistant...")
        
        with sync_playwright() as p:
            context = self._create_browser_context(p, force_visible=True)
            page = context.pages[0] if context.pages else context.new_page()
            
            if not self.ensure_login(page, context):
                self.log("Login check unverified. Stopping session.", "WARNING")
                try:
                    context.close()
                except Exception:
                    pass
                return

            keywords = self.config.get("keywords", ["Operations Management"])
            max_apps = self.config.get("max_applications_per_run", 30)

            for keyword in keywords:
                if self.stop_requested:
                    self.log("Session stopped by user.", "WARNING")
                    break
                if self.applied_count >= max_apps:
                    self.log(f"Daily application target reached ({self.applied_count}/{max_apps}).", "SUCCESS")
                    break
                self.log(f"\n🔍 Searching for keyword: '{keyword}'")
                self.process_keyword(page, keyword)

            self.log(f"\n🏁 Session summary: Applied: {self.applied_count} | Skipped: {self.skipped_count} | Failed: {self.failed_count}", "SUCCESS")
            try:
                context.close()
            except Exception:
                pass

    def ensure_login_manual_only(self):
        self.log("Opening Chrome window for Naukri login setup...")
        with sync_playwright() as p:
            context = self._create_browser_context(p, force_visible=True)
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded")
            self.log("🌐 Chrome is open! Please log into your Naukri account in the Chrome window. Close Chrome when finished.", "SUCCESS")
            while len(context.pages) > 0:
                try:
                    time.sleep(2)
                except Exception:
                    break

    def is_logged_in_check(self, page, context):
        try:
            current_url = page.url.lower()
            if "mnjuser/homepage" in current_url or "mnjuser/profile" in current_url:
                return True

            profile_elem = page.query_selector(".nI-gD-profile, .profile-edit, a[href*='mnjuser/profile'], .user-name, div[class*='profile']")
            if profile_elem and profile_elem.is_visible():
                return True

            cookies = context.cookies()
            for c in cookies:
                if c.get("name") in ["nls", "Naukri_User", "n_user"]:
                    return True
        except Exception:
            pass
        return False

    def ensure_login(self, page, context):
        self.log("Checking Naukri authentication session...")
        try:
            page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded")
            self.random_sleep(2, 3)
        except Exception as e:
            self.log(f"Failed to navigate to Naukri login: {e}", "ERROR")
            return False

        if self.is_logged_in_check(page, context):
            self.log("✅ Logged in session confirmed!", "SUCCESS")
            return True

        self.log("⚠️ NOT LOGGED IN! Opening Login Window...", "WARNING")
        
        email = self.config.get("naukri_email", "").strip()
        pwd = self.config.get("naukri_password", "").strip()

        if email and pwd:
            self.log(f"🔑 Attempting auto-login for '{email}'...")
            try:
                user_inp = page.query_selector("#usernameField, input[placeholder*='Username'], input[placeholder*='Email']")
                if user_inp:
                    user_inp.fill(email)
                    self.random_sleep(1, 2)
                
                pwd_inp = page.query_selector("#passwordField, input[type='password']")
                if pwd_inp:
                    pwd_inp.fill(pwd)
                    self.random_sleep(1, 2)

                submit_btn = page.query_selector("button[type='submit'], button:has-text('Login')")
                if submit_btn:
                    submit_btn.click()
                    self.random_sleep(3, 5)
            except Exception as ex:
                self.log(f"Auto-login typing note: {ex}", "WARNING")

        if self.is_logged_in_check(page, context):
            self.log("✅ Logged in successfully via credentials!", "SUCCESS")
            return True

        self.log("👉 Please complete Login / OTP in the opened Chrome browser window.", "INFO")
        self.log("Waiting for login completion (up to 3 minutes)...", "INFO")

        for i in range(60):
            if self.stop_requested:
                return False
            time.sleep(3)
            if self.is_logged_in_check(page, context):
                self.log("✅ Login detected! Starting application process...", "SUCCESS")
                return True

        self.log("Login timeout. Please click 'Open Chrome & Log In To Naukri' in the app to log in manually.", "ERROR")
        return False

    def process_keyword(self, page, keyword):
        locations = ",".join(self.config.get("locations", []))
        exp = self.config.get("experience_years", 4)
        
        encoded_kw = urllib.parse.quote(keyword)
        encoded_loc = urllib.parse.quote(locations)
        search_url = f"https://www.naukri.com/{encoded_kw.lower().replace(' ', '-')}-jobs-in-{encoded_loc.lower().replace(' ', '-')}?k={encoded_kw}&l={encoded_loc}&experience={exp}"
        
        self.log(f"Loading search URL: {search_url}")
        try:
            page.goto(search_url, wait_until="domcontentloaded")
            self.random_sleep(3, 5)
        except Exception as e:
            self.log(f"Error loading search page: {e}", "ERROR")
            return

        current_page_num = 1
        max_pages = 5

        while current_page_num <= max_pages and self.applied_count < self.config.get("max_applications_per_run", 30):
            if self.stop_requested:
                break
                
            self.log(f"Processing Search Page {current_page_num} for '{keyword}'...")
            
            try:
                page.wait_for_selector(".srp-jobtuple-wrapper, article.jobTuple, .cust-job-tuple", timeout=8000)
            except Exception:
                self.log(f"No job tuples found on page {current_page_num}.", "WARNING")
                break

            job_cards = page.query_selector_all(".srp-jobtuple-wrapper, article.jobTuple, .cust-job-tuple")
            self.log(f"Found {len(job_cards)} job cards on page {current_page_num}.")

            job_list = []
            for card in job_cards:
                try:
                    title_elem = card.query_selector("a.title, a.title.ellipsis")
                    if not title_elem:
                        continue
                    url = title_elem.get_attribute("href")
                    title = title_elem.text_content().strip()
                    
                    comp_elem = card.query_selector("a.subTitle, span.comp-name")
                    company = comp_elem.text_content().strip() if comp_elem else "Unknown"
                    job_id = card.get_attribute("data-job-id") or url

                    # Check for on-card 'Applied' badge
                    card_applied = card.query_selector(".already-applied, span:has-text('Applied'), .applied-badge")
                    if card_applied or self.tracker.is_applied(job_id, url, title, company):
                        self.log(f"⏭ Skipping duplicate: {title} @ {company}", "INFO")
                        self.skipped_count += 1
                        continue
                    
                    job_list.append({"id": job_id, "title": title, "company": company, "url": url})
                except Exception:
                    continue

            for job in job_list:
                if self.stop_requested or self.applied_count >= self.config.get("max_applications_per_run", 30):
                    break
                self.apply_to_job(page.context, job)
                self.random_sleep()

            current_page_num += 1
            try:
                next_btn = page.query_selector("a.styles_btn-secondary__2ZaG4:has-text('Next'), a:has-text('Next')")
                if next_btn and next_btn.is_visible():
                    next_btn.click()
                    self.random_sleep(3, 5)
                else:
                    break
            except Exception:
                break

    def apply_to_job(self, context, job):
        self.log(f"👉 Opening Job: {job['title']} @ {job['company']}")
        new_page = context.new_page()
        try:
            new_page.goto(job['url'], wait_until="domcontentloaded")
            self.random_sleep(2, 4)

            apply_btn = new_page.query_selector(
                "button#apply-button, button.apply-button, button:has-text('Apply'), button:has-text('Apply on Naukri'), .apply-button-container button"
            )

            if not apply_btn:
                already_applied = new_page.query_selector(".already-applied, span:has-text('Already Applied'), .applied-msg")
                if already_applied:
                    self.log(f"ℹ️ Already applied previously on page.", "INFO")
                    self.tracker.log_application(job['id'], job['title'], job['company'], "", job['url'], status="ALREADY_APPLIED")
                    self.skipped_count += 1
                else:
                    self.log(f"⚠️ No Apply button found. Skipping.", "WARNING")
                    self.tracker.log_application(job['id'], job['title'], job['company'], "", job['url'], status="SKIPPED", notes="No button")
                    self.skipped_count += 1
                new_page.close()
                return

            btn_text = apply_btn.text_content().strip()
            if "company site" in btn_text.lower() or "external" in btn_text.lower():
                self.log(f"ℹ️ External redirect job ({btn_text}). Logging as external.", "INFO")
                self.tracker.log_application(job['id'], job['title'], job['company'], "", job['url'], status="EXTERNAL", notes=btn_text)
                self.skipped_count += 1
                new_page.close()
                return

            self.log(f"  Clicking '{btn_text}'...")
            apply_btn.click()
            self.random_sleep(2, 4)

            applied_success = self.solve_application_questionnaires(new_page, job)

            if applied_success:
                self.log(f"🎯 SUCCESS: Applied to {job['title']} at {job['company']}", "SUCCESS")
                self.tracker.log_application(job['id'], job['title'], job['company'], "", job['url'], status="APPLIED")
                self.applied_count += 1
            else:
                self.log(f"⚠️ Application submitted with unverified status for {job['title']}", "WARNING")
                self.tracker.log_application(job['id'], job['title'], job['company'], "", job['url'], status="APPLIED_UNVERIFIED")
                self.applied_count += 1

        except Exception as e:
            self.log(f"❌ Application Error for {job['title']}: {e}", "ERROR")
            self.tracker.log_application(job['id'], job['title'], job['company'], "", job['url'], status="FAILED", notes=str(e)[:100])
            self.failed_count += 1
        finally:
            try:
                new_page.close()
            except Exception:
                pass

    def solve_application_questionnaires(self, page, job):
        """
        Advanced Multi-Step Questionnaire & Form Solver.
        Iteratively fills all experience prompts, options, text fields, and file uploads.
        """
        exp_years = self.config.get("experience_years", 4)
        curr_ctc = self.config.get("current_ctc_lpa", 4.0)
        exp_ctc = self.config.get("expected_ctc_lpa", 6.5)
        notice_str = self.config.get("notice_period_str", "15 Days or less")
        notice_days = self.config.get("notice_period_days", 15)
        resume_file = self.config.get("resume_path", "")
        relocate = self.config.get("willing_to_relocate", True)
        target_locations = self.config.get("locations", ["Bangalore", "Gurugram", "Delhi NCR"])

        for step in range(1, 10):
            self.random_sleep(1, 2)
            
            success_elem = page.query_selector(
                ".applied-msg, .success-title, div:has-text('Successfully Applied'), div:has-text('Application Sent'), .apply-message"
            )
            if success_elem and success_elem.is_visible():
                self.log("  Verified success message displayed!", "SUCCESS")
                return True

            overlay = page.query_selector(
                ".botContainer, .questionnaire-container, div[role='dialog'], .drawer-wrapper, .modal-content, .chatbot-container"
            )
            
            if not overlay or not overlay.is_visible():
                if step > 1:
                    return True
                time.sleep(1)
                continue

            self.log(f"  📋 Solving Questionnaire Step {step}...")

            # 1. Fill Experience & Text Inputs
            inputs = overlay.query_selector_all("input[type='text'], input[type='number'], input:not([type]), textarea")
            for inp in inputs:
                try:
                    if not inp.is_visible() or inp.get_attribute("value"):
                        continue
                    
                    placeholder = (inp.get_attribute("placeholder") or "").lower()
                    name_attr = (inp.get_attribute("name") or "").lower()
                    id_attr = (inp.get_attribute("id") or "").lower()
                    label_text = ""
                    try:
                        parent = inp.evaluate_handle("node => node.closest('div, label, tr, td')")
                        label_text = parent.as_element().text_content().lower() if parent else ""
                    except Exception:
                        pass
                    
                    context_str = f"{placeholder} {name_attr} {id_attr} {label_text}"

                    # Comprehensive Experience Field Matcher
                    if any(k in context_str for k in [
                        "exp", "year", "experience", "relevant", "total experience", 
                        "industry experience", "domain experience", "duration", "how many years"
                    ]):
                        inp.fill(str(exp_years))
                        self.log(f"    Filled Work Experience: {exp_years} Years")
                    elif any(k in context_str for k in ["current ctc", "present ctc", "current salary", "present salary"]):
                        inp.fill(str(curr_ctc))
                        self.log(f"    Filled Current CTC: {curr_ctc} LPA")
                    elif any(k in context_str for k in ["expected ctc", "expected salary"]):
                        inp.fill(str(exp_ctc))
                        self.log(f"    Filled Expected CTC: {exp_ctc} LPA")
                    elif any(k in context_str for k in ["notice", "days"]):
                        inp.fill(str(notice_days))
                        self.log(f"    Filled Notice Period: {notice_days} Days")
                    elif any(k in context_str for k in ["location", "city", "current location"]):
                        loc_val = target_locations[0] if target_locations else "Bangalore"
                        inp.fill(loc_val)
                        self.log(f"    Filled Location: {loc_val}")
                    else:
                        smart_ans = f"I have {exp_years} years of total work experience in Operations Management, Finance, and AML compliance."
                        inp.fill(smart_ans)
                        self.log(f"    Filled Custom Field: '{smart_ans[:45]}...'")
                except Exception:
                    pass

            # 2. File Upload for Resume
            if resume_file and os.path.exists(resume_file):
                file_inputs = overlay.query_selector_all("input[type='file']")
                for finp in file_inputs:
                    try:
                        finp.set_input_files(resume_file)
                        self.log(f"    Attached Resume: {os.path.basename(resume_file)}")
                    except Exception:
                        pass

            # 3. Radio Buttons & Experience Option Chips
            radio_labels = overlay.query_selector_all("label, .chip, .option, span.radio-label, div.radio-option, button.option")
            for rlbl in radio_labels:
                try:
                    txt = rlbl.text_content().strip()
                    txt_lower = txt.lower()

                    # Match Experience options (e.g. '4 Years', '3-5 Yrs')
                    if any(e in txt_lower for e in [f"{exp_years} year", f"{exp_years} yr", "3-5", "4-5", "3-6", "4-6"]):
                        rlbl.click()
                        self.log(f"    Selected Experience Option: '{txt}'")
                        break
                    # Match Notice Period options
                    elif any(n in txt_lower for n in ["15 days", "15 days or less", "immediate", "serving notice"]):
                        rlbl.click()
                        self.log(f"    Selected Notice Option: '{txt}'")
                        break
                    # Match Relocation / Yes-No options
                    elif relocate and any(y in txt_lower for y in ["yes", "ready to relocate", "willing to relocate"]):
                        rlbl.click()
                        self.log(f"    Selected Option: '{txt}'")
                        break
                    # Match Location options
                    elif any(loc.lower() in txt_lower for loc in target_locations):
                        rlbl.click()
                        self.log(f"    Selected Location Option: '{txt}'")
                        break
                except Exception:
                    pass

            # 4. Click Submit / Next / Continue button
            submit_btn = overlay.query_selector(
                "button:has-text('Submit'), button:has-text('Save'), button:has-text('Next'), button:has-text('Continue'), button:has-text('Save & Apply'), button.submit-btn, input[type='submit']"
            )
            
            if submit_btn and submit_btn.is_visible():
                btn_name = submit_btn.text_content().strip()
                self.log(f"    Clicking '{btn_name}'...")
                submit_btn.click()
                self.random_sleep(2, 3)
            else:
                primary_btn = overlay.query_selector("button.btn-primary, button[type='submit']")
                if primary_btn and primary_btn.is_visible():
                    primary_btn.click()
                    self.random_sleep(2, 3)

        return True

if __name__ == "__main__":
    bot = NaukriBot()
    bot.start()
