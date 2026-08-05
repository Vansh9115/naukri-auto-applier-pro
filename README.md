# Naukri Auto-Applier Pro 🚀 (Desktop Software)

A modern desktop application and intelligent Playwright automation assistant to search for job opportunities on Naukri.com, auto-fill step-by-step application forms/questionnaires, attach your resume, and track all applications.

---

## ✨ Features

- **🖥 Desktop GUI Software**: Built with CustomTkinter. Configure job keywords, target locations, experience, CTC, notice period, and resume file directly in the app.
- **🧠 Smart Multi-Step Questionnaire Solver**:
  - Automatically handles all chatbot drawers (`.botContainer`, `.chatbot-container`), slide-in prompts, and modal dialogs (`div[role='dialog']`).
  - Fills out Work Experience, Current CTC, Expected CTC, Notice Period, Location, and custom screening questions.
  - Automatically uploads your Resume PDF file when prompted (`input[type='file']`).
  - Auto-selects options for Notice Period (e.g. *15 Days or less*, *Immediate*), Relocation willingness (*Yes*), and location preferences.
- **🔑 Session Management**: Launches Chrome with a persistent user data directory (`./naukri_user_data`). You log in once, and future runs remain logged in automatically.
- **📊 Real-Time Log & Application Tracker**: Live color-coded activity logs inside the app console, plus CSV logging in `applied_jobs.csv`.

---

## 🚀 How to Run

1. Simply double-click **`run_app.bat`** in `C:\Users\vansh\.gemini\antigravity\scratch\naukri-auto-apply`.
   *(Or run `python app.py` in terminal)*
2. The Desktop App window will open.
3. Confirm/enter your details (Keywords, Locations, Experience, CTC, Notice Period, Resume path).
4. Click **🚀 Save & Start Applying**.
5. If logging in for the first time, click **🔑 Log In To Naukri Profile** to open Chrome and log in.

---

## 📁 File Overview

- `app.py`: Main Desktop GUI Software window
- `naukri_bot.py`: Automation engine & Smart Questionnaire Solver Loop
- `tracker.py`: Application logging & deduplication database
- `config.json`: Persistent user settings & search criteria
- `run_app.bat`: Double-click launcher script
