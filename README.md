# Auto-Shorts-Generator

Automated pipeline that downloads a trending YouTube video, extracts the most engaging segment, and crops it to 9:16 vertical format.

## Quick Start

```bash
# Create a virtual environment
python3 -m venv .venv && source .venv/bin/activate

# Install runtime + dev dependencies
pip install -e ".[dev]"

# Run the grabber module standalone
python -m auto_shorts_generator.grabber

# Run the test suite
pytest -v
```

## Project Structure

```
auto_shorts_generator/
├── __init__.py      # Package marker
├── config.py        # Centralized configuration
├── logger.py        # Shared logging factory
├── grabber.py       # Phase 1 – Trending video downloader
├── analyzer.py      # Phase 2 – Audio-based highlight extractor
├── cropper.py       # Phase 3 – Smart 9:16 vertical crop
└── main.py          # Phase 4 – Assembly pipeline
tests/
├── test_grabber.py  # 16 tests
├── test_analyzer.py # 13 tests
├── test_cropper.py  # 15 tests
└── test_main.py     # 13 tests  (57 total)
```

## Phases

| Phase | Module        | Status |
|-------|--------------|--------|
| 1     | `grabber.py`  | ✅ Done |
| 2     | `analyzer.py` | ✅ Done |
| 3     | `cropper.py`  | ✅ Done |
| 4     | `main.py`     | ✅ Done |
