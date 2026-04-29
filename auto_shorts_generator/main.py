"""
main.py – Phase 4: Assembly Pipeline
=====================================

Orchestrates the full Auto-Shorts-Generator flow:

    1. **Grab** → download the #1 trending YouTube video
    2. **Analyze** → find the most energetic 45–60 s highlight
    3. **Crop** → letterbox to 9:16 vertical 

Ensures temporary files are cleaned up after the final output is rendered.
"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path
from typing import Optional

from auto_shorts_generator import config
from auto_shorts_generator.logger import get_logger
from auto_shorts_generator.grabber import grab, GrabberError
from auto_shorts_generator.analyzer import analyze, AnalyzerError
from auto_shorts_generator.cropper import crop_video, CropperError

log = get_logger(__name__)

class PipelineError(Exception):
    """Top-level error wrapping any phase failure."""


def _cleanup_temp_dir() -> None:
    if config.TEMP_DIR.exists():
        shutil.rmtree(config.TEMP_DIR)
        log.info("🧹  Cleaned up temp directory: %s", config.TEMP_DIR)


def _format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.1f}s"


def run_pipeline(
    *,
    output_path: Optional[Path | str] = None,
    cleanup: bool = True,
) -> Path:
    
    if output_path is None:
        output_path = config.CROPPED_PATH
    output_path = Path(output_path)

    pipeline_start = time.time()

    log.info("=" * 60)
    log.info("🚀  AUTO-SHORTS-GENERATOR PIPELINE STARTING")
    log.info("=" * 60)

    # ── Phase 1: Download ────────────────────────────────────────────
    try:
        log.info("─" * 60)
        log.info("📥  PHASE 1/3: Downloading trending video …")
        log.info("─" * 60)

        phase_start = time.time()
        raw_video = grab()
        elapsed = time.time() - phase_start

        log.info(
            "✅  Phase 1 complete (%s) → %s",
            _format_elapsed(elapsed),
            raw_video.name,
        )
    except GrabberError as exc:
        log.error("❌  Phase 1 FAILED: %s", exc)
        raise PipelineError(f"Download phase failed: {exc}") from exc

    # ── Phase 2: Analyse & extract highlight ─────────────────────────
    try:
        log.info("─" * 60)
        log.info("🔍  PHASE 2/3: Extracting highlight segment …")
        log.info("─" * 60)

        phase_start = time.time()
        highlight_clip = analyze(raw_video)
        elapsed = time.time() - phase_start

        log.info(
            "✅  Phase 2 complete (%s) → %s",
            _format_elapsed(elapsed),
            highlight_clip.name,
        )
    except AnalyzerError as exc:
        log.error("❌  Phase 2 FAILED: %s", exc)
        raise PipelineError(f"Analyse phase failed: {exc}") from exc

    # ── Phase 3: Letterboxing ────────────────────────────────────────
    try:
        log.info("─" * 60)
        log.info("📐  PHASE 3/3: Letterboxing to 9:16 vertical …")
        log.info("─" * 60)

        phase_start = time.time()
        # Ensure we explicitly assign the output_path parameter
        final_short = crop_video(highlight_clip, output_path=output_path)
        elapsed = time.time() - phase_start

        log.info(
            "✅  Phase 3 complete (%s) → %s",
            _format_elapsed(elapsed),
            final_short.name,
        )
    except CropperError as exc:
        log.error("❌  Phase 3 FAILED: %s", exc)
        raise PipelineError(f"Crop phase failed: {exc}") from exc

    # ── Cleanup ──────────────────────────────────────────────────────
    if cleanup:
        _cleanup_temp_dir()

    total_elapsed = time.time() - pipeline_start
    log.info("=" * 60)
    log.info(
        "🎬  PIPELINE COMPLETE in %s → %s",
        _format_elapsed(total_elapsed),
        final_short,
    )
    log.info("=" * 60)

    return final_short


if __name__ == "__main__":
    try:
        result = run_pipeline()
        print(f"\n🎬  Final short → {result}")
    except PipelineError as err:
        print(f"\n❌  Pipeline failed: {err}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        log.warning("⚠️  Pipeline interrupted by user.")
        sys.exit(130)