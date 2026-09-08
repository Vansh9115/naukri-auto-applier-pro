# 🎁 How to Share Naukri Auto-Applier Pro with a Non-Technical Friend

If your friend is non-technical and cannot install complex tools on their laptop, here are the easiest ways to give them this application.

---

## 🏆 Option 0: The standalone .exe (No Python, no pip installs — just Chrome)

This is the version to send a friend on a laptop where you don't want them installing anything except Chrome, which almost everyone already has.

### Step 1: Build it (on your machine, once)
```bash
pip install pyinstaller
pyinstaller NaukriAutoApplierPro.spec
```
This produces `dist/NaukriAutoApplierPro.exe` — a single file with Python, Flask, Playwright, pandas, etc. all bundled inside. It's large (~50MB) because of that, which is expected.

### Step 2: Send them just the .exe
Zip and send `dist/NaukriAutoApplierPro.exe` on its own — nothing else from the repo is needed.

### Step 3: What your friend needs
1. **The only mandatory install: Google Chrome.** The bot drives your friend's real installed Chrome (not a hidden bot browser) so Google sign-in works normally. If they don't have it: [google.com/chrome](https://www.google.com/chrome/).
2. Put `NaukriAutoApplierPro.exe` in its own folder (it creates `config.json`, `uploads/`, `naukri_chrome_profile/`, and `applied_jobs.csv` next to itself the first time it runs).
3. Double-click it. A console window opens, then their browser opens to `http://localhost:5000` automatically.
4. Fill in the form (keywords, CTC, resume, etc.) and click **Login with Google**, then **Start Applying**.

No Python, no `pip install`, no `playwright install` — all of that is baked into the .exe.

---

## ⚡ Option 1: Send them a ZIP file (Python required)

### Step 1: Download the ZIP from GitHub
1. Go to your GitHub repository:
   **[https://github.com/Vansh9115/naukri-auto-applier-pro](https://github.com/Vansh9115/naukri-auto-applier-pro)**
2. Click the green **`Code`** button at the top right.
3. Select **`Download ZIP`** (or share this direct link with your friend: `https://github.com/Vansh9115/naukri-auto-applier-pro/archive/refs/heads/main.zip`).

### Step 2: What your friend needs to do
Send your friend these 3 simple instructions:
1. **Extract/Unzip** the downloaded folder on their desktop.
2. Double-click **`Double_Click_To_Start.bat`**.
3. Their web browser will automatically open to `http://localhost:5000` with the Web App Dashboard ready to apply!

---

## 🌐 Option 2: Share a Public Web Link (No Download Needed!)

If you want your friend to use the application from their browser without downloading anything at all:

### Step 1: Start the Web App on your laptop
1. Run **`run_web_app.bat`** on your computer.

### Step 2: Make it public with 1 simple command
Run this command in terminal to generate a live public link:
```bash
npx localtunnel --port 5000
```
This will output a live web link (e.g. `https://naukri-auto-applier.loca.lt`).

### Step 3: Send the link to your friend
Your friend opens `https://naukri-auto-applier.loca.lt` on their phone, laptop, or tablet without downloading or installing anything!
