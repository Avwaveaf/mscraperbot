***

# Auto-Shorts-Generator 🎬

An automated, lightweight Python pipeline that fetches a trending YouTube video, extracts the most engaging segment, and perfectly formats it into a 9:16 vertical Short with letterboxing. 

Built to be modular, robust, and highly performant.

## ⚙️ How It Works (The Phases)

This pipeline executes in four distinct phases. If a phase fails, the pipeline halts gracefully.

| Phase | Module | Status | Description |
| :--- | :--- | :--- | :--- |
| **1** | `grabber.py` | ✅ Done | Bypasses bot detection via iOS client routing to download the #1 trending video (max 1080p). Automatically skips live streams and premieres. |
| **2** | `analyzer.py` | ✅ Done | Scans the audio waveform to locate the highest-energy 45-60 second window (the "climax" or highlight). |
| **3** | `cropper.py` | ✅ Done | Rapidly scales the 16:9 highlight to fit a vertical frame and pads the remaining space with a cinematic black letterbox using FFmpeg. |
| **4** | `main.py` | ✅ Done | Orchestrates the sequence, manages temporary file cleanup, and provides detailed terminal logging. |

---

## 🛠️ Prerequisites

Before installing the Python packages, your machine **must** have the following system-level tools installed:

1. **Python 3.11** (Highly recommended for optimal compatibility with underlying C++ media libraries).
2. **FFmpeg** (Required by `yt-dlp` to merge high-res audio/video tracks, and by `cropper.py` for letterboxing).

---

## 💻 Installation

Choose your operating system below for step-by-step first-time setup instructions.

### 🍎 macOS Setup

**1. Install System Dependencies (via Homebrew)**
Open your terminal and install Python 3.11 and FFmpeg.
```bash
brew install python@3.11
brew install ffmpeg
```

**2. Clone and Setup the Environment**
Navigate to your project folder, create a clean virtual environment, and activate it.
```bash
# Create the virtual environment using Python 3.11
python3.11 -m venv .venv

# Activate the environment
source .venv/bin/activate
```

**3. Install the Project**
```bash
# Install the project and all runtime/development dependencies
pip install -e ".[dev]"
```

### 🪟 Windows Setup

**1. Install System Dependencies**
* **Python:** Download and install Python 3.11 from the [official Python website](https://www.python.org/downloads/). *Crucial: Ensure you check the box that says "Add Python to PATH" during installation.*
* **FFmpeg:** The easiest way to install FFmpeg on Windows is via the Winget package manager. Open Command Prompt or PowerShell and run:
    ```powershell
    winget install ffmpeg
    ```
    *(Restart your terminal after installation so Windows registers the `ffmpeg` command).*

**2. Clone and Setup the Environment**
Open your terminal, navigate to the project directory, and run:
```powershell
# Create the virtual environment
python -m venv .venv

# Activate the environment
.venv\Scripts\activate
```

**3. Install the Project**
```powershell
# Install the project and all runtime/development dependencies
pip install -e ".[dev]"
```

---

## 🚀 Usage

Ensure your virtual environment is activated (`source .venv/bin/activate` on Mac, `.venv\Scripts\activate` on Windows).

**Run the Complete Pipeline:**
This will execute the full Phase 1 ➔ Phase 4 sequence and output the final `output_short.mp4`.
```bash
python -m auto_shorts_generator.main
```

**Run Modules Standalone:**
Because the architecture is highly modular, you can run and test individual phases.
```bash
# Test just the downloader
python -m auto_shorts_generator.grabber

# Test the cropper on a specific local file
python -m auto_shorts_generator.cropper path/to/your/local_video.mp4
```

**Run the Test Suite:**
```bash
pytest -v
```

---

## 📂 Project Structure

```text
auto_shorts_generator/
├── __init__.py      # Package marker
├── config.py        # Centralized configuration (timeouts, paths, resolutions)
├── logger.py        # Shared logging factory for unified terminal output
├── grabber.py       # Phase 1 module
├── analyzer.py      # Phase 2 module
├── cropper.py       # Phase 3 module
└── main.py          # Phase 4 orchestrator
tests/
├── test_grabber.py  # 16 tests
├── test_analyzer.py # 13 tests
├── test_cropper.py  # 15 tests
└── test_main.py     # 13 tests  (57 total)
```