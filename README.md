# Context Clipboard

A lightweight Windows clipboard manager that remembers what you copied, where it came from, and lets you instantly search your full copy history.

Context Clipboard runs silently in the system tray, captures every clipboard change with source context (app name, window title, timestamp, optional screenshot), and stores it in a local SQLite database with full-text search. Press **Win+Shift+V** (or **Ctrl+Shift+V** fallback) from anywhere to recall any past clip.

---

## Features

- **Background monitoring** silently tracks clipboard changes via Win32 APIs
- **Context awareness** stores source app, window title, timestamp, and optional screenshot
- **Full-text search** by content, app name, or window title with prefix matching
- **Global hotkey** summons the search window instantly with **Win+Shift+V** (will be **Ctrl+Shift+V** in case of error)
- **System tray integration** minimizes to tray, close from tray menu
- **Auto-startup** via registry toggle in Settings
- **Screenshots** of full-desktop on every copy
- **Deduplication** with SHA-256 hash prevents storing the same text twice

---

## Folder Structure

```
context_clipboard/
├── clipboard_service.py        # Background service: Win32 clipboard listener, DB, screenshots
├── clipboard_gui.py            # Tkinter GUI: search, settings, system tray icon
├── requirements.txt            # Python dependencies
├── build.bat                   # One-click PyInstaller build + desktop shortcut
├── installer/
│   └── ContextClipboard.nsi    # NSIS installer script (Windows setup wizard)
└── README.md                   # This file
```

---

## Setup & Installation

### Method 1 — Download Pre-built Installer (Recommended)

1. Go to the **[GitHub Releases](https://github.com/Arnav-Agrawal-987/context_clipboard/releases)** page.
2. Download the latest `ContextClipboard-Setup-vX.X.X.exe`.
3. Run the installer. It will install to `%LOCALAPPDATA%\Programs\ContextClipboard` and create:
   - A **Start Menu** shortcut
   - A **Desktop** shortcut
4. Launch **Context Clipboard** from the Start Menu or Desktop.
5. The app starts in the system tray. Right-click the tray icon to open Search or Exit.

> **Note:** The installer is per-user and does not require Administrator privileges.

---

### Method 2 — Build from Source

**Prerequisites:** Python 3.12+, pip, and [NSIS](https://nsis.sourceforge.io/Download) (optional, only if you want to build the installer).

```powershell
# 1. Clone the repository
git clone https://github.com/Arnav-Agrawal-987/context_clipboard.git
cd ContextClipboard

# 2. Create a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Build the executable + create a Desktop shortcut
.\build.bat
```

After `build.bat` finishes:
- The executable is at `dist\ContextClipboard\ContextClipboard.exe`
- A shortcut has been placed on your **Desktop**
- You can run the app directly from the Desktop shortcut or the `dist` folder

**Optional — Build the NSIS installer:**

1. Install [NSIS](https://nsis.sourceforge.io/Download).
2. Open `installer\ContextClipboard.nsi` in the NSIS compiler (or right-click → "Compile NSIS Script").
3. The installer `.exe` will be generated next to the `.nsi` file.

---

## Usage

| Action | How |
|--------|-----|
| Open search | **Win+Shift+V** (global) or right-click tray icon → **Open** |
| Hide window | Click **X** to minimize to tray |
| Exit app | Right-click tray icon → **Exit** |
| Toggle screenshots | **Settings** → check *Capture screenshots* |
| Toggle auto-start | **Settings** → check *Start with Windows* |
| Search syntax | Hover over the **ℹ️** icon beside the search bar |

---
