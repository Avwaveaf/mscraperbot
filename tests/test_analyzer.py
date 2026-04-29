"""
Unit tests for auto_shorts_generator.analyzer
==============================================

Tests mock ffmpeg/librosa calls so they run offline and fast.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import numpy as np
import pytest

from auto_shorts_generator.analyzer import (
    AnalyzerError,
    AudioExtractionError,
    ClipExtractionError,
    HighlightResult,
    VideoTooShortError,
    _best_window,
    _compute_rms_energy,
    extract_clip,
    find_highlight,
    analyze,
)


# ── _best_window unit tests ─────────────────────────────────────────────


class TestBestWindow:
    """Tests for the sliding-window energy search."""

    def test_finds_peak_in_middle(self) -> None:
        """A loud spike in the middle should be found."""
        sr = 22050
        # 120 seconds of audio at ~43 fps (hop=512)
        n_frames = 5200
        times = np.linspace(0, 120, n_frames)
        rms = np.ones(n_frames) * 0.1

        # Insert a loud region at 40-90s (~1733 to 3900 frames)
        loud_start = int(n_frames * 40 / 120)
        loud_end = int(n_frames * 90 / 120)
        rms[loud_start:loud_end] = 0.9

        result = _best_window(times, rms, min_dur=45, max_dur=60)

        assert result.start_time >= 35.0  # should land near the loud region
        assert result.end_time <= 95.0
        assert result.avg_energy > 0.5

    def test_video_shorter_than_min_returns_full(self) -> None:
        """A 30s video should return 0 → 30 as the highlight."""
        times = np.linspace(0, 30, 1300)
        rms = np.ones(1300) * 0.5

        result = _best_window(times, rms, min_dur=45, max_dur=60)

        assert result.start_time == 0.0
        assert result.end_time == 30.0
        assert result.duration == 30.0

    def test_empty_arrays(self) -> None:
        """Edge case: empty input."""
        result = _best_window(np.array([]), np.array([]), min_dur=45, max_dur=60)
        assert result.duration == 0.0

    def test_exact_min_duration_video(self) -> None:
        """A 45s video should return the full video."""
        times = np.linspace(0, 45, 1950)
        rms = np.random.rand(1950) * 0.5

        result = _best_window(times, rms, min_dur=45, max_dur=60)

        # Should use the full video since it's exactly min_dur
        assert result.start_time == 0.0
        assert result.end_time == 45.0


class TestComputeRmsEnergy:
    """Tests for the RMS computation wrapper."""

    def test_returns_matching_lengths(self) -> None:
        audio = np.random.randn(22050 * 10).astype(np.float32)  # 10s
        times, rms = _compute_rms_energy(audio, sr=22050)
        assert len(times) == len(rms)
        assert len(times) > 0

    def test_silent_audio_has_low_rms(self) -> None:
        audio = np.zeros(22050 * 5, dtype=np.float32)
        _, rms = _compute_rms_energy(audio, sr=22050)
        assert np.all(rms < 0.001)


# ── find_highlight tests ────────────────────────────────────────────────


class TestFindHighlight:
    """Tests for the main analysis entry point."""

    def test_raises_on_missing_file(self) -> None:
        with pytest.raises(AnalyzerError, match="not found"):
            find_highlight(Path("/nonexistent/video.mp4"))

    @mock.patch("auto_shorts_generator.analyzer._extract_audio_to_wav")
    @mock.patch("auto_shorts_generator.analyzer.librosa")
    def test_raises_on_short_audio(
        self, mock_librosa: mock.MagicMock, mock_extract: mock.MagicMock, tmp_path: Path
    ) -> None:
        video = tmp_path / "short.mp4"
        video.write_bytes(b"\x00" * 100)
        wav = tmp_path / "audio.wav"
        wav.write_bytes(b"\x00" * 100)
        mock_extract.return_value = wav

        # 0.5 seconds of audio
        mock_librosa.load.return_value = (np.zeros(11025, dtype=np.float32), 22050)
        mock_librosa.get_duration.return_value = 0.5

        with pytest.raises(VideoTooShortError, match="too short"):
            find_highlight(video)

    @mock.patch("auto_shorts_generator.analyzer._extract_audio_to_wav")
    @mock.patch("auto_shorts_generator.analyzer.librosa")
    def test_returns_highlight_for_normal_video(
        self, mock_librosa: mock.MagicMock, mock_extract: mock.MagicMock, tmp_path: Path
    ) -> None:
        video = tmp_path / "normal.mp4"
        video.write_bytes(b"\x00" * 100)
        wav = tmp_path / "audio.wav"
        wav.write_bytes(b"\x00" * 100)
        mock_extract.return_value = wav

        # 120 seconds of audio
        audio_data = np.random.randn(22050 * 120).astype(np.float32)
        mock_librosa.load.return_value = (audio_data, 22050)
        mock_librosa.get_duration.return_value = 120.0

        # Wire through real librosa functions for RMS
        import librosa as real_librosa
        mock_librosa.feature.rms.side_effect = real_librosa.feature.rms
        mock_librosa.frames_to_time.side_effect = real_librosa.frames_to_time

        result = find_highlight(video)

        assert isinstance(result, HighlightResult)
        assert 45 <= result.duration <= 60
        assert result.avg_energy > 0


# ── extract_clip tests ──────────────────────────────────────────────────


class TestExtractClip:
    """Tests for the ffmpeg clip extraction."""

    @mock.patch("auto_shorts_generator.analyzer.subprocess.run")
    def test_successful_extraction(
        self, mock_run: mock.MagicMock, tmp_path: Path
    ) -> None:
        video = tmp_path / "source.mp4"
        video.write_bytes(b"\x00" * 1024)
        output = tmp_path / "clip.mp4"

        def create_output(*args, **kwargs):
            output.write_bytes(b"\x00" * 512)

        mock_run.side_effect = create_output

        result = extract_clip(video, 10.0, 55.0, output)
        assert result.exists()

    @mock.patch("auto_shorts_generator.analyzer.subprocess.run")
    def test_raises_on_ffmpeg_failure(
        self, mock_run: mock.MagicMock, tmp_path: Path
    ) -> None:
        import subprocess
        video = tmp_path / "source.mp4"
        video.write_bytes(b"\x00" * 100)

        mock_run.side_effect = subprocess.CalledProcessError(1, "ffmpeg")

        with pytest.raises(ClipExtractionError, match="ffmpeg"):
            extract_clip(video, 0, 45, tmp_path / "out.mp4")


# ── analyze() convenience function ──────────────────────────────────────


class TestAnalyze:
    """Tests for the one-call convenience wrapper."""

    def test_wires_find_and_extract(self, tmp_path: Path) -> None:
        video = tmp_path / "v.mp4"
        video.write_bytes(b"\x00")
        out = tmp_path / "clip.mp4"

        highlight = HighlightResult(
            start_time=10.0, end_time=55.0, duration=45.0, avg_energy=0.8
        )

        with (
            mock.patch(
                "auto_shorts_generator.analyzer.find_highlight",
                return_value=highlight,
            ) as mock_find,
            mock.patch(
                "auto_shorts_generator.analyzer.extract_clip",
                return_value=out,
            ) as mock_extract,
        ):
            result = analyze(video, output_path=out)

        mock_find.assert_called_once_with(video)
        mock_extract.assert_called_once_with(video, 10.0, 55.0, out)
        assert result == out


# ── Exception hierarchy ─────────────────────────────────────────────────


class TestExceptionHierarchy:
    def test_all_inherit_from_analyzer_error(self) -> None:
        assert issubclass(AudioExtractionError, AnalyzerError)
        assert issubclass(VideoTooShortError, AnalyzerError)
        assert issubclass(ClipExtractionError, AnalyzerError)
