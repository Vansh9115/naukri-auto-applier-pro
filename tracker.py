import os
import csv
from datetime import datetime

class JobTracker:
    def __init__(self, filename="applied_jobs.csv"):
        self.filename = filename
        self.applied_ids = set()
        self.applied_signatures = set()
        self._init_csv()

    def _init_csv(self):
        file_exists = os.path.exists(self.filename)
        if file_exists:
            with open(self.filename, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if 'job_id' in row and row['job_id']:
                        self.applied_ids.add(row['job_id'].strip())
                    if 'url' in row and row['url']:
                        self.applied_ids.add(row['url'].strip())
                    title = (row.get('title') or '').strip().lower()
                    company = (row.get('company') or '').strip().lower()
                    if title and company:
                        self.applied_signatures.add(f"{title}||{company}")
        else:
            with open(self.filename, mode='w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'job_id', 'title', 'company', 
                    'location', 'url', 'status', 'notes'
                ])

    def is_applied(self, job_id, url="", title="", company=""):
        if job_id and job_id.strip() in self.applied_ids:
            return True
        if url and url.strip() in self.applied_ids:
            return True
        if title and company:
            sig = f"{title.strip().lower()}||{company.strip().lower()}"
            if sig in self.applied_signatures:
                return True
        return False

    def log_application(self, job_id, title, company, location, url, status="APPLIED", notes=""):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.filename, mode='a', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                timestamp, job_id, title, company, 
                location, url, status, notes
            ])
        if job_id:
            self.applied_ids.add(job_id.strip())
        if url:
            self.applied_ids.add(url.strip())
        if title and company:
            self.applied_signatures.add(f"{title.strip().lower()}||{company.strip().lower()}")
        print(f" Recorded: [{status}] {title} at {company}")

    def get_analytics_summary(self):
        """ Generates analytics breakdown of all job application records """
        if not os.path.exists(self.filename):
            return {"total": 0, "applied": 0, "already_applied": 0, "external": 0, "failed": 0, "records": []}

        records = []
        applied_count = 0
        already_applied_count = 0
        external_count = 0
        failed_count = 0

        with open(self.filename, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(row)
                st = (row.get('status') or '').upper()
                if st in ['APPLIED', 'APPLIED_UNVERIFIED']:
                    applied_count += 1
                elif st == 'ALREADY_APPLIED':
                    already_applied_count += 1
                elif st == 'EXTERNAL':
                    external_count += 1
                elif st in ['FAILED', 'SKIPPED']:
                    failed_count += 1

        return {
            "total": len(records),
            "applied": applied_count,
            "already_applied": already_applied_count,
            "external": external_count,
            "failed": failed_count,
            "records": records
        }

    def generate_html_report(self, report_filename="application_report.html"):
        """ Generates a clean HTML analytics dashboard report """
        data = self.get_analytics_summary()
        records = data["records"]
        
        rows_html = ""
        for r in reversed(records[-100:]):  # Last 100 applications
            status_color = "#22c55e" if r['status'] in ['APPLIED', 'APPLIED_UNVERIFIED'] else ("#eab308" if r['status'] == 'EXTERNAL' else "#ef4444")
            rows_html += f"""
            <tr>
                <td>{r.get('timestamp', '')}</td>
                <td><strong>{r.get('title', '')}</strong></td>
                <td>{r.get('company', '')}</td>
                <td><span style="background:{status_color}; color:#fff; padding:3px 8px; border-radius:4px; font-size:12px; font-weight:bold;">{r.get('status', '')}</span></td>
                <td><a href="{r.get('url', '#')}" target="_blank">View Job</a></td>
            </tr>
            """

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Naukri Application Analytics Report</title>
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }}
                .container {{ max-width: 1100px; margin: 0 auto; }}
                h1 {{ color: #38bdf8; }}
                .metrics {{ display: flex; gap: 15px; margin-bottom: 25px; }}
                .card {{ background: #1e293b; padding: 20px; border-radius: 8px; flex: 1; text-align: center; border: 1px solid #334155; }}
                .card .num {{ font-size: 32px; font-weight: bold; margin-top: 5px; color: #38bdf8; }}
                table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 8px; overflow: hidden; }}
                th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #334155; }}
                th {{ background: #0f172a; color: #94a3b8; font-size: 13px; text-transform: uppercase; }}
                a {{ color: #38bdf8; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Naukri Application Analytics Report</h1>
                <p>Report generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
                <div class="metrics">
                    <div class="card"><div>Total Jobs Logged</div><div class="num">{data['total']}</div></div>
                    <div class="card"><div>Successfully Applied</div><div class="num" style="color:#22c55e;">{data['applied']}</div></div>
                    <div class="card"><div>Already Applied / Duplicate</div><div class="num" style="color:#eab308;">{data['already_applied']}</div></div>
                    <div class="card"><div>External Redirects</div><div class="num" style="color:#a855f7;">{data['external']}</div></div>
                    <div class="card"><div>Failed / Skipped</div><div class="num" style="color:#ef4444;">{data['failed']}</div></div>
                </div>
                <h2>Recent Applications Activity</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Timestamp</th>
                            <th>Job Title</th>
                            <th>Company</th>
                            <th>Status</th>
                            <th>Link</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </div>
        </body>
        </html>
        """
        
        with open(report_filename, "w", encoding="utf-8") as f:
            f.write(html_content)
        return os.path.abspath(report_filename)
