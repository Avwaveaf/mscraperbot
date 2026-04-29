"""
Unit tests for auto_shorts_generator.main
==========================================

Tests mock all phase modules so the pipeline logic is tested in isolation.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest import mock

import pytest

from auto_shorts_generator import config
from auto_shorts_generator.grabber import GrabberError
from auto_shorts_generator.analyzer import AnalyzerError
from auto_shorts_generator.cropper import CropperError
from auto_shorts_generator.main import (
    PipelineError,
    _cleanup_temp_dir,
    _format_elapsed,
    run_pipeline,
)


# ── _format_elapsed tests ───────────────────────────────────────────────


class TestFormatElapsed:
    def test_seconds_only(self) -> None:
        assert _format_elapsed(42.5) == "42.5s"

    def test_minutes_and_seconds(self) -> None:
        assert _format_elapsed(125.3) == "2m 5.3s"

    def test_zero(self) -> None:
        assert _format_elapsed(0.0) == "0.0s"


# ── _cleanup_temp_dir tests ─────────────────────────────────────────────


class TestCleanupTempDir:
    def test_removes_existing_temp_dir(self, tmp_path: Path) -> None:
        temp = tmp_path / "temp"
        temp.mkdir()
        (temp / "file.txt").write_text("data")

        with mock.patch.object(config, "TEMP_DIR", temp):
            _cleanup_temp_dir()

        assert not temp.exists()

    def test_noop_if_missing(self, tmp_path: Path) -> None:
        temp = tmp_path / "nonexistent"
        with mock.patch.object(config, "TEMP_DIR", temp):
            _cleanup_temp_dir()  # should not raise


# ── run_pipeline tests ──────────────────────────────────────────────────


class TestRunPipeline:
    """Tests for the full pipeline orchestration."""

    def _mock_all_phases(self, tmp_path: Path):
        """Return context managers mocking grab, analyze, crop."""
        raw = tmp_path / "raw.mp4"
        raw.write_bytes(b"\x00" * 1024)
        highlight = tmp_path / "highlight.mp4"
        highlight.write_bytes(b"\x00" * 512)
        output = tmp_path / "output_short.mp4"
        output.write_bytes(b"\x00" * 256)

        return (
            mock.patch("auto_shorts_generator.main.grab", return_value=raw),
            mock.patch("auto_shorts_generator.main.analyze", return_value=highlight),
            mock.patch("auto_shorts_generator.main.crop_video", return_value=output),
            mock.patch("auto_shorts_generator.main._cleanup_temp_dir"),
            output,
        )

    def test_successful_pipeline(self, tmp_path: Path) -> None:
        m_grab, m_analyze, m_crop, m_clean, output = self._mock_all_phases(tmp_path)

        with m_grab, m_analyze, m_crop, m_clean:
            result = run_pipeline(output_path=output, cleanup=True)

        assert result == output

    def test_calls_all_phases_in_order(self, tmp_path: Path) -> None:
        m_grab, m_analyze, m_crop, m_clean, output = self._mock_all_phases(tmp_path)

        with m_grab as mg, m_analyze as ma, m_crop as mc, m_clean:
            run_pipeline(output_path=output)

        mg.assert_called_once()
        ma.assert_called_once()
        mc.assert_called_once()

    def test_cleanup_called_when_enabled(self, tmp_path: Path) -> None:
        m_grab, m_analyze, m_crop, m_clean, output = self._mock_all_phases(tmp_path)

        with m_grab, m_analyze, m_crop, m_clean as mc:
            run_pipeline(output_path=output, cleanup=True)

        mc.assert_called_once()

    def test_cleanup_skipped_when_disabled(self, tmp_path: Path) -> None:
        m_grab, m_analyze, m_crop, m_clean, output = self._mock_all_phases(tmp_path)

        with m_grab, m_analyze, m_crop, m_clean as mc:
            run_pipeline(output_path=output, cleanup=False)

        mc.assert_not_called()

    def test_phase1_failure_raises_pipeline_error(self, tmp_path: Path) -> None:
        with mock.patch(
            "auto_shorts_generator.main.grab",
            side_effect=GrabberError("network down"),
        ):
            with pytest.raises(PipelineError, match="Download phase failed"):
                run_pipeline(output_path=tmp_path / "out.mp4")

    def test_phase2_failure_raises_pipeline_error(self, tmp_path: Path) -> None:
        raw = tmp_path / "raw.mp4"
        raw.write_bytes(b"\x00" * 1024)

        with (
            mock.patch("auto_shorts_generator.main.grab", return_value=raw),
            mock.patch(
                "auto_shorts_generator.main.analyze",
                side_effect=AnalyzerError("audio corrupt"),
            ),
        ):
            with pytest.raises(PipelineError, match="Analyse phase failed"):
                run_pipeline(output_path=tmp_path / "out.mp4")

    def test_phase3_failure_raises_pipeline_error(self, tmp_path: Path) -> None:
        raw = tmp_path / "raw.mp4"
        raw.write_bytes(b"\x00" * 1024)
        highlight = tmp_path / "highlight.mp4"
        highlight.write_bytes(b"\x00" * 512)

        with (
            mock.patch("auto_shorts_generator.main.grab", return_value=raw),
            mock.patch("auto_shorts_generator.main.analyze", return_value=highlight),
            mock.patch(
                "auto_shorts_generator.main.crop_video",
                side_effect=CropperError("face model missing"),
            ),
        ):
            with pytest.raises(PipelineError, match="Crop phase failed"):
                run_pipeline(output_path=tmp_path / "out.mp4")

    def test_phase_errors_wrap_original_cause(self, tmp_path: Path) -> None:
        """PipelineError.__cause__ should be the original phase error."""
        original = GrabberError("root cause")
        with mock.patch(
            "auto_shorts_generator.main.grab",
            side_effect=original,
        ):
            with pytest.raises(PipelineError) as exc_info:
                run_pipeline(output_path=tmp_path / "out.mp4")

            assert exc_info.value.__cause__ is original
