"""
cropper.py – Phase 3: Vertical Letterboxing (No Subtitles)
==========================================================
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from auto_shorts_generator import config
from auto_shorts_generator.logger import get_logger

log = get_logger(__name__)

class CropperError(Exception):
    pass

class VideoWriteError(CropperError):
    pass

def crop_video(
    video_path: Path | str,
    output_path: Optional[Path | str] = None,
) -> Path:
    
    video_path = Path(video_path).resolve()
    if not video_path.exists():
        raise VideoWriteError(f"Source video not found: {video_path}")

    if output_path is None:
        output_path = config.CROPPED_PATH
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    target_w = getattr(config, "OUTPUT_WIDTH", 1080)
    target_h = getattr(config, "OUTPUT_HEIGHT", 1920)

    log.info("─" * 60)
    log.info("📐  PHASE 3: Letterboxing video to %dx%d...", target_w, target_h)

    # Scale to width, pad the remaining height with black
    vf_filter = f"scale={target_w}:-1,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", vf_filter,
        "-c:v", "libx264",
        "-preset", "fast",    
        "-crf", "23",         
        "-c:a", "copy",       
        str(output_path),
    ]
    
    try:
        log.info("Executing FFmpeg command...")
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    except subprocess.CalledProcessError as exc:
        error_log = exc.stderr.decode(errors="ignore")
        log.error("FFmpeg failed with error:\n%s", error_log)
        raise VideoWriteError(f"ffmpeg mux failed: {exc}") from exc

    if not output_path.exists():
        raise VideoWriteError(f"ffmpeg ran but {output_path} was not created.")

    log.info("✅  Vertical short created: %s", output_path.name)
    return output_path

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m auto_shorts_generator.cropper <video_path>")
        sys.exit(1)
    try:
        result = crop_video(sys.argv[1], "output_short.mp4")
        print(f"\n🎬  Final letterboxed short → {result}")
    except CropperError as err:
        print(f"\n❌  Cropper failed: {err}", file=sys.stderr)
        sys.exit(1)