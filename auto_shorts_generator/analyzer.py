"""
analyzer.py – Phase 2: Highlight Extractor
==========================================

Responsibilities
----------------
1. Extract the audio track from a video file.
2. Compute a rolling RMS (loudness) energy curve using librosa.
3. Find the contiguous 45–60 s window with the highest average energy.
4. Extract that segment to a new video file using moviepy.

Public API
----------
- ``find_highlight(video_path, min_dur, max_dur)`` → HighlightResult
- ``extract_clip(video_path, start, end, out)``    → Path
- ``analyze(video_path)``                          → Path   ← one-call convenience
"""

from __future__ import annotations

import dataclasses
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import librosa
import numpy as np

from auto_shorts_generator import config
from auto_shorts_generator.logger import get_logger

log = get_logger(__name__)


# ── Data structures ──────────────────────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class HighlightResult:
    """Immutable container for the detected highlight window."""

    start_time: float   # seconds
    end_time: float     # seconds
    duration: float     # seconds
    avg_energy: float   # mean RMS over the window


# ── Custom exceptions ────────────────────────────────────────────────────


class AnalyzerError(Exception):
    """Base error for the analyzer module."""


class AudioExtractionError(AnalyzerError):
    """Raised when audio cannot be extracted from the video."""


class VideoTooShortError(AnalyzerError):
    """Raised when the source video is shorter than the minimum highlight."""


class ClipExtractionError(AnalyzerError):
    """Raised when ffmpeg fails to cut the highlight clip."""


# ── Internal helpers ─────────────────────────────────────────────────────


def _extract_audio_to_wav(video_path: Path) -> Path:
    """
    Use ffmpeg CLI to extract audio as a mono WAV into a temp file.

    Returns the Path to the temporary WAV file (caller must clean up).
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    wav_path = Path(tmp.name)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",                       # no video
        "-acodec", "pcm_s16le",      # 16-bit PCM
        "-ar", str(config.AUDIO_SAMPLE_RATE),
        "-ac", "1",                  # mono
        str(wav_path),
    ]

    log.info("Extracting audio → %s", wav_path)
    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            timeout=120,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        wav_path.unlink(missing_ok=True)
        raise AudioExtractionError(
            f"ffmpeg audio extraction failed: {exc}"
        ) from exc

    if not wav_path.exists() or wav_path.stat().st_size == 0:
        wav_path.unlink(missing_ok=True)
        raise AudioExtractionError("ffmpeg produced an empty or missing WAV file.")

    return wav_path


def _compute_rms_energy(
    audio: np.ndarray,
    sr: int,
    hop_length: int = config.RMS_HOP_LENGTH,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute per-frame RMS energy and corresponding timestamps.

    Returns
    -------
    (times, rms)
        times : 1-D float array of frame centre times in seconds.
        rms   : 1-D float array of RMS values per frame.
    """
    rms = librosa.feature.rms(y=audio, hop_length=hop_length)[0]
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)
    return times, rms


def _best_window(
    times: np.ndarray,
    rms: np.ndarray,
    min_dur: float,
    max_dur: float,
) -> HighlightResult:
    """
    Sliding-window search over all durations in [min_dur, max_dur] (1 s steps)
    to find the window with the highest mean RMS.
    """
    total_duration = times[-1] if len(times) > 0 else 0.0

    # Edge case: video is shorter than the minimum window
    if total_duration <= min_dur:
        return HighlightResult(
            start_time=0.0,
            end_time=total_duration,
            duration=total_duration,
            avg_energy=float(np.mean(rms)) if len(rms) > 0 else 0.0,
        )

    best = HighlightResult(start_time=0, end_time=min_dur, duration=min_dur, avg_energy=-1.0)
    frame_rate = times[1] - times[0] if len(times) > 1 else 1.0

    # Try every integer duration from min_dur to max_dur
    for dur in range(int(min_dur), int(min(max_dur, total_duration)) + 1):
        window_frames = int(dur / frame_rate)
        if window_frames < 1 or window_frames > len(rms):
            continue

        # Efficient rolling mean via cumulative sum
        cumsum = np.cumsum(np.insert(rms, 0, 0))
        rolling = (cumsum[window_frames:] - cumsum[:-window_frames]) / window_frames

        if len(rolling) == 0:
            continue

        idx = int(np.argmax(rolling))
        mean_energy = float(rolling[idx])

        if mean_energy > best.avg_energy:
            start_sec = float(times[idx]) if idx < len(times) else 0.0
            end_sec = min(start_sec + dur, total_duration)
            best = HighlightResult(
                start_time=round(start_sec, 3),
                end_time=round(end_sec, 3),
                duration=round(end_sec - start_sec, 3),
                avg_energy=round(mean_energy, 6),
            )

    log.info(
        "Best highlight window: %.1fs → %.1fs (%.1fs, energy=%.4f)",
        best.start_time,
        best.end_time,
        best.duration,
        best.avg_energy,
    )
    return best


# ── Public API ───────────────────────────────────────────────────────────


def find_highlight(
    video_path: Path | str,
    *,
    min_dur: float = config.HIGHLIGHT_MIN_SEC,
    max_dur: float = config.HIGHLIGHT_MAX_SEC,
) -> HighlightResult:
    """
    Analyse the audio of *video_path* and return the most energetic window.

    Parameters
    ----------
    video_path : Path
        Source video file.
    min_dur, max_dur : float
        Desired highlight duration range in seconds.

    Returns
    -------
    HighlightResult
        Start/end times and average energy of the best window.

    Raises
    ------
    AudioExtractionError
        If audio cannot be extracted.
    VideoTooShortError
        If the video is shorter than 1 second (essentially no audio).
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise AnalyzerError(f"Video file not found: {video_path}")

    # Extract audio to temp WAV
    wav_path = _extract_audio_to_wav(video_path)

    try:
        log.info("Loading audio for RMS analysis …")
        audio, sr = librosa.load(str(wav_path), sr=config.AUDIO_SAMPLE_RATE, mono=True)

        audio_duration = librosa.get_duration(y=audio, sr=sr)
        log.info("Audio duration: %.2f s (sr=%d)", audio_duration, sr)

        if audio_duration < 1.0:
            raise VideoTooShortError(
                f"Video audio is only {audio_duration:.1f}s — too short to analyse."
            )

        times, rms = _compute_rms_energy(audio, sr)
        return _best_window(times, rms, min_dur, max_dur)
    finally:
        wav_path.unlink(missing_ok=True)
        log.debug("Cleaned up temp WAV: %s", wav_path)


def extract_clip(
    video_path: Path | str,
    start_time: float,
    end_time: float,
    output_path: Optional[Path | str] = None,
) -> Path:
    """
    Cut a segment from *video_path* between *start_time* and *end_time*.

    Uses ffmpeg with stream-copy for speed (no re-encoding).

    Parameters
    ----------
    video_path : Path
        Source video.
    start_time, end_time : float
        Segment boundaries in seconds.
    output_path : Path, optional
        Destination file (default from config).

    Returns
    -------
    Path
        Absolute path to the extracted clip.

    Raises
    ------
    ClipExtractionError
        If ffmpeg fails.
    """
    video_path = Path(video_path)
    if output_path is None:
        output_path = config.EXTRACTED_CLIP_PATH
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    duration = end_time - start_time
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start_time:.3f}",
        "-i", str(video_path),
        "-t", f"{duration:.3f}",
        "-c", "copy",                # stream copy — no re-encoding
        "-avoid_negative_ts", "1",
        str(output_path),
    ]

    log.info(
        "Extracting clip %.1fs → %.1fs (%.1fs) → %s",
        start_time, end_time, duration, output_path,
    )

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise ClipExtractionError(f"ffmpeg clip extraction failed: {exc}") from exc

    if not output_path.exists():
        raise ClipExtractionError(f"ffmpeg ran but {output_path} was not created.")

    log.info(
        "✅  Clip extracted: %s (%.2f MB)",
        output_path,
        output_path.stat().st_size / 1_048_576,
    )
    return output_path.resolve()


def analyze(
    video_path: Path | str,
    *,
    output_path: Optional[Path | str] = None,
) -> Path:
    """
    One-call convenience: find the highlight window and extract it.

    Returns
    -------
    Path
        Absolute path to the highlight clip.
    """
    video_path = Path(video_path)
    result = find_highlight(video_path)
    return extract_clip(video_path, result.start_time, result.end_time, output_path)


# ── CLI entry-point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m auto_shorts_generator.analyzer <video_path>")
        sys.exit(1)

    try:
        clip = analyze(sys.argv[1])
        print(f"\n🎯  Highlight clip → {clip}")
    except AnalyzerError as err:
        print(f"\n❌  Analyzer failed: {err}", file=sys.stderr)
        sys.exit(1)
