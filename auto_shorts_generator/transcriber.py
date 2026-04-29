"""
transcriber.py – Phase 2.5: Auto-Subtitles
==========================================

Responsibilities
----------------
1. Load the OpenAI Whisper AI model.
2. Scan the audio of the downloaded video.
3. Generate an accurately timed .srt subtitle file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import whisper
from whisper.utils import get_writer

from auto_shorts_generator import config
from auto_shorts_generator.logger import get_logger

log = get_logger(__name__)

class TranscriberError(Exception):
    pass

def generate_subtitles(
    video_path: Path | str, 
    output_dir: Optional[Path | str] = None
) -> Path:
    """
    Transcribe the video and output an .srt file.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise TranscriberError(f"Cannot transcribe missing file: {video_path}")

    if output_dir is None:
        output_dir = video_path.parent
    else:
        output_dir = Path(output_dir)

    log.info("─" * 60)
    log.info("🎙️  PHASE 2.5: Generating subtitles with Whisper AI...")
    
    try:
        # 'base' is incredibly fast and highly accurate for clear speech. 
        # You can upgrade to 'small' or 'medium' later if you need extreme accuracy.
        log.info("Loading Whisper 'base' model into memory...")
        model = whisper.load_model("base")
        
        log.info("Listening and transcribing... (this takes a moment)")
        result = model.transcribe(str(video_path))
        
        # Whisper automatically writes the .srt file based on the results
        writer = get_writer("srt", str(output_dir))
        
        # Whisper saves the file with the same name as the video, but with .srt
        writer(result, str(video_path))
        
        srt_path = output_dir / f"{video_path.stem}.srt"
        
        if not srt_path.exists():
            raise TranscriberError("Whisper finished, but the .srt file was not created.")
            
        log.info("✅  Subtitles generated: %s", srt_path.name)
        return srt_path

    except Exception as exc:
        raise TranscriberError(f"Failed to generate subtitles: {exc}") from exc