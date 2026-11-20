# 🤖 AI Browser Agent (Python & Chrome Extension)

An autonomous AI browser copilot powered by Google Gemini and Playwright. Just give it any natural language command, and it automatically opens your browser, types into search boxes, clicks buttons, scrolls, navigates between sites, and reports back the final result!

---

## ⚡ Quick Start with Python (Recommended)

### Option 1: Double-Click Launcher (Windows)
Simply double-click:
```
run.bat
```
This opens the desktop interface where you can enter your command and watch Chrome open and automate in real-time.

---

### Option 2: Run via Terminal

#### Desktop App (GUI):
```bash
python app.py
```

#### Command Line Interface (CLI):
```bash
python agent.py "Search Google for latest tech news today and summarize"
```
Or interactively:
```bash
python agent.py
```

---

## 🔑 Setup Gemini API Key

1. Get a free API key from [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Enter it into the app window (or paste it into `config.json`).
3. It is automatically saved and remembered for future runs.

---

## 🌟 How It Works

1. **Launches Your Real Browser**: Opens Google Chrome (or Microsoft Edge) on your screen so you can see every action.
2. **DOM Perception**: Scans visible links, buttons, inputs, and text content, assigning clean numbered identifiers.
3. **Gemini Reasoning**: The AI decides whether to click an element, type text, press Enter, scroll, or navigate to a new site.
4. **Visual Highlights**: Highlights the targeted element on the page with an animated glow right before clicking or typing so you can watch what it's doing.
5. **Completion**: Reads the final answer and reports it to you.

---

## 📁 Project Structure

```
├── run.bat            # One-click Windows desktop launcher
├── app.py             # Tkinter desktop GUI app
├── agent.py           # Command-line interface runner
├── browser_agent.py   # Core Playwright + Gemini AI automation engine
├── config.json        # Saved settings (API key, model, browser)
│
├── manifest.json      # Chrome Extension Manifest V3 (if using as extension)
├── popup.html         # Extension popup HTML
├── popup.css          # Extension styling
├── popup.js           # Extension controller
└── background.js      # Extension service worker
```
