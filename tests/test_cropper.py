"""
Unit tests for auto_shorts_generator.cropper
=============================================

Tests mock OpenCV, MediaPipe, and ffmpeg so they run offline and fast.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import cv2
import numpy as np
import pytest

from auto_shorts_generator.cropper import (
    CropperError,
    VideoReadError,
    VideoWriteError,
    _clamp_crop_x,
    _smooth_positions,
    crop_video,
)


# ── _smooth_positions tests ─────────────────────────────────────────────


class TestSmoothPositions:
    """Tests for the moving-average smoothing function."""

    def test_smoothing_reduces_jitter(self) -> None:
        """A jittery signal should become smoother."""
        jittery = [100, 500, 100, 500, 100, 500, 100, 500, 100, 500,
                    100, 500, 100, 500, 100, 500, 100, 500, 100, 500]
        smoothed = _smooth_positions(jittery, window=5)

        # The smoothed std should be lower than the jittery std
        assert np.std(smoothed) < np.std(jittery)

    def test_constant_signal_unchanged(self) -> None:
        """A constant signal should pass through unchanged."""
        constant = [300] * 20
        smoothed = _smooth_positions(constant, window=5)
        assert smoothed == constant

    def test_empty_input(self) -> None:
        assert _smooth_positions([]) == []

    def test_single_element(self) -> None:
        assert _smooth_positions([500], window=5) == [500]

    def test_window_of_one_is_identity(self) -> None:
        data = [10, 20, 30, 40, 50]
        assert _smooth_positions(data, window=1) == data

    def test_preserves_length(self) -> None:
        data = list(range(100))
        result = _smooth_positions(data, window=15)
        assert len(result) == len(data)

    def test_gradual_ramp_stays_monotonic(self) -> None:
        """A smoothly increasing signal should remain roughly monotonic."""
        ramp = list(range(0, 1000, 10))  # 100 points
        smoothed = _smooth_positions(ramp, window=7)
        # Allow tiny non-monotonicity from edge correction but overall trend
        diffs = [smoothed[i + 1] - smoothed[i] for i in range(len(smoothed) - 1)]
        assert sum(1 for d in diffs if d >= 0) > len(diffs) * 0.9


# ── _clamp_crop_x tests ─────────────────────────────────────────────────


class TestClampCropX:
    """Tests for the X-coordinate clamping utility."""

    def test_centre_within_bounds(self) -> None:
        """Crop centred in a 1920px frame with 608px crop width."""
        left = _clamp_crop_x(960, frame_width=1920, crop_width=608)
        assert left == 960 - 304  # 656

    def test_clamps_left_edge(self) -> None:
        """Face near the left edge should clamp to 0."""
        left = _clamp_crop_x(100, frame_width=1920, crop_width=608)
        assert left == 0

    def test_clamps_right_edge(self) -> None:
        """Face near the right edge should clamp so crop stays in frame."""
        left = _clamp_crop_x(1900, frame_width=1920, crop_width=608)
        assert left == 1920 - 608  # 1312

    def test_exact_frame_width_crop(self) -> None:
        """When crop equals frame width, left should always be 0."""
        left = _clamp_crop_x(500, frame_width=1000, crop_width=1000)
        assert left == 0


# ── crop_video tests ────────────────────────────────────────────────────


class TestCropVideo:
    """Tests for the main crop pipeline."""

    def test_raises_on_missing_video(self, tmp_path: Path) -> None:
        """Non-existent source should raise VideoReadError."""
        with mock.patch("cv2.VideoCapture") as MockCap:
            instance = MockCap.return_value
            instance.isOpened.return_value = False

            with pytest.raises(VideoReadError):
                crop_video(tmp_path / "nonexistent.mp4", tmp_path / "out.mp4")

    @mock.patch("auto_shorts_generator.cropper.subprocess.run")
    @mock.patch("auto_shorts_generator.cropper.compute_crop_positions")
    @mock.patch("cv2.VideoWriter")
    @mock.patch("cv2.VideoCapture")
    @mock.patch("cv2.resize")
    def test_successful_crop_pipeline(
        self,
        mock_resize: mock.MagicMock,
        mock_cap_cls: mock.MagicMock,
        mock_writer_cls: mock.MagicMock,
        mock_positions: mock.MagicMock,
        mock_ffmpeg: mock.MagicMock,
        tmp_path: Path,
    ) -> None:
        """Full pipeline with mocked I/O should produce the output file."""
        source = tmp_path / "highlight.mp4"
        source.write_bytes(b"\x00" * 100)
        output = tmp_path / "output_short.mp4"

        # Mock crop positions
        mock_positions.return_value = [960] * 5

        # Mock VideoCapture
        cap = mock_cap_cls.return_value
        cap.isOpened.return_value = True
        cap.get.side_effect = lambda prop: {
            cv2.CAP_PROP_FRAME_WIDTH: 1920,
            cv2.CAP_PROP_FRAME_HEIGHT: 1080,
            cv2.CAP_PROP_FPS: 30.0,
            cv2.CAP_PROP_FRAME_COUNT: 5,
        }.get(prop, 0)

        # Return 5 frames then stop
        fake_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        cap.read.side_effect = [
            (True, fake_frame),
            (True, fake_frame),
            (True, fake_frame),
            (True, fake_frame),
            (True, fake_frame),
            (False, None),
        ]

        # Mock VideoWriter
        writer = mock_writer_cls.return_value
        writer.isOpened.return_value = True

        # Mock resize
        mock_resize.return_value = np.zeros(
            (1920, 1080, 3), dtype=np.uint8
        )

        # Mock ffmpeg to create the output file
        def create_output(*args, **kwargs):
            output.write_bytes(b"\x00" * 256)

        mock_ffmpeg.side_effect = create_output

        result = crop_video(source, output)

        assert result == output.resolve()
        assert writer.write.call_count == 5
        mock_ffmpeg.assert_called_once()

    @mock.patch("auto_shorts_generator.cropper.compute_crop_positions")
    @mock.patch("cv2.VideoCapture")
    def test_raises_on_writer_failure(
        self,
        mock_cap_cls: mock.MagicMock,
        mock_positions: mock.MagicMock,
        tmp_path: Path,
    ) -> None:
        source = tmp_path / "highlight.mp4"
        source.write_bytes(b"\x00" * 100)

        mock_positions.return_value = [960] * 5

        cap = mock_cap_cls.return_value
        cap.isOpened.return_value = True
        cap.get.side_effect = lambda prop: {
            cv2.CAP_PROP_FRAME_WIDTH: 1920,
            cv2.CAP_PROP_FRAME_HEIGHT: 1080,
            cv2.CAP_PROP_FPS: 30.0,
            cv2.CAP_PROP_FRAME_COUNT: 5,
        }.get(prop, 0)

        with mock.patch("cv2.VideoWriter") as mock_writer_cls:
            writer = mock_writer_cls.return_value
            writer.isOpened.return_value = False

            with pytest.raises(VideoWriteError):
                crop_video(source, tmp_path / "out.mp4")


# ── Exception hierarchy ─────────────────────────────────────────────────


class TestExceptionHierarchy:
    def test_all_inherit_from_cropper_error(self) -> None:
        assert issubclass(VideoReadError, CropperError)
        assert issubclass(VideoWriteError, CropperError)
