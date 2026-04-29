"""
Centralized configuration for the Auto-Shorts-Generator pipeline.

All magic numbers, paths, and tunables live here so every module
can import a single source of truth.
"""

from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────
OUTPUT_DIR = Path("output")
TEMP_DIR = OUTPUT_DIR / "temp"
RAW_VIDEO_FILENAME = "temp_raw.mp4"
RAW_VIDEO_PATH = TEMP_DIR / RAW_VIDEO_FILENAME

# ── Downloader (grabber) settings ────────────────────────────────────────
MAX_RESOLUTION = 1080          # px – cap height to keep processing fast
DOWNLOAD_TIMEOUT_SEC = 120     # socket-level read timeout for yt-dlp
DOWNLOAD_RETRIES = 3           # number of retry attempts on transient errors
TRENDING_URL = "https://www.youtube.com/gaming"
MAX_VIDEOS_TO_FETCH = 1        # how many trending videos to consider

# ── Format selection ─────────────────────────────────────────────────────
# yt-dlp format string: best video up to 1080p + best audio, merged to mp4
YT_DLP_FORMAT = (
    f"bestvideo[height<={MAX_RESOLUTION}][ext=mp4]"
    f"+bestaudio[ext=m4a]/best[height<={MAX_RESOLUTION}][ext=mp4]/best"
)

# ── Analyzer (highlight extractor) settings ──────────────────────────────
HIGHLIGHT_MIN_SEC = 45           # minimum highlight duration in seconds
HIGHLIGHT_MAX_SEC = 60           # maximum highlight duration in seconds
AUDIO_SAMPLE_RATE = 22050        # librosa default SR for analysis
RMS_HOP_LENGTH = 512             # hop length for RMS computation
EXTRACTED_CLIP_FILENAME = "temp_highlight.mp4"
EXTRACTED_CLIP_PATH = TEMP_DIR / EXTRACTED_CLIP_FILENAME

# ── Cropper (smart vertical crop) settings ───────────────────────────────
TARGET_ASPECT = (9, 16)          # vertical short aspect ratio
OUTPUT_WIDTH = 1080              # final output width in px
OUTPUT_HEIGHT = 1920             # final output height in px
FACE_DETECTION_CONFIDENCE = 0.5  # MediaPipe min detection confidence
SMOOTHING_WINDOW = 15            # moving-average window for X-coordinate smoothing
FACE_DETECT_SKIP_FRAMES = 3     # run face detection every N frames for performance
CROPPED_FILENAME = "output_short.mp4"
CROPPED_PATH = OUTPUT_DIR / CROPPED_FILENAME

# ── Logging ──────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s | %(name)-18s | %(levelname)-7s | %(message)s"
