# 🎁 How to Share Naukri Auto-Applier Pro with a Non-Technical Friend

If your friend is non-technical and cannot install complex tools on their laptop, here are the **2 easiest ways** to give them this application:

---

## ⚡ Option 1: Send them a ZIP file (Simplest & Most Portable)

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
