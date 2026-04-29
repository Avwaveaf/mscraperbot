"""
Unit tests for auto_shorts_generator.grabber
=============================================

These tests mock yt-dlp entirely so they run offline and fast.
"""

from __future__ import annotations

import socket
from pathlib import Path
from unittest import mock

import pytest

from auto_shorts_generator import config
from auto_shorts_generator.grabber import (
    DownloadError,
    GrabberError,
    NoTrendingVideosError,
    download_video,
    fetch_trending_urls,
    grab,
)


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_output(tmp_path: Path) -> Path:
    """Return a temp file path for download tests."""
    return tmp_path / "test_video.mp4"


# ── fetch_trending_urls tests ────────────────────────────────────────────


class TestFetchTrendingUrls:
    """Tests for the trending URL scraper."""

    def test_returns_urls_on_success(self) -> None:
        fake_info = {
            "entries": [
                {"id": "abc123"},
                {"id": "def456"},
            ],
        }
        with mock.patch("auto_shorts_generator.grabber.yt_dlp.YoutubeDL") as MockYDL:
            instance = MockYDL.return_value.__enter__.return_value
            instance.extract_info.return_value = fake_info

            urls = fetch_trending_urls(max_results=2)

        assert len(urls) == 2
        assert urls[0] == "https://www.youtube.com/watch?v=abc123"
        assert urls[1] == "https://www.youtube.com/watch?v=def456"

    def test_respects_max_results(self) -> None:
        fake_info = {
            "entries": [
                {"id": f"vid{i}"} for i in range(10)
            ],
        }
        with mock.patch("auto_shorts_generator.grabber.yt_dlp.YoutubeDL") as MockYDL:
            instance = MockYDL.return_value.__enter__.return_value
            instance.extract_info.return_value = fake_info

            urls = fetch_trending_urls(max_results=3)

        assert len(urls) == 3

    def test_raises_when_no_entries(self) -> None:
        fake_info = {"entries": []}
        with mock.patch("auto_shorts_generator.grabber.yt_dlp.YoutubeDL") as MockYDL:
            instance = MockYDL.return_value.__enter__.return_value
            instance.extract_info.return_value = fake_info

            with pytest.raises(NoTrendingVideosError):
                fetch_trending_urls()

    def test_raises_on_empty_info(self) -> None:
        with mock.patch("auto_shorts_generator.grabber.yt_dlp.YoutubeDL") as MockYDL:
            instance = MockYDL.return_value.__enter__.return_value
            instance.extract_info.return_value = None

            with pytest.raises(NoTrendingVideosError):
                fetch_trending_urls()

    def test_raises_on_network_error(self) -> None:
        with mock.patch("auto_shorts_generator.grabber.yt_dlp.YoutubeDL") as MockYDL:
            instance = MockYDL.return_value.__enter__.return_value
            instance.extract_info.side_effect = socket.timeout("timed out")

            with pytest.raises(NoTrendingVideosError, match="timed out"):
                fetch_trending_urls()

    def test_handles_full_url_entries(self) -> None:
        """Entries that already contain full URLs should be kept as-is."""
        full_url = "https://www.youtube.com/watch?v=xyz789"
        fake_info = {"entries": [{"id": full_url}]}
        with mock.patch("auto_shorts_generator.grabber.yt_dlp.YoutubeDL") as MockYDL:
            instance = MockYDL.return_value.__enter__.return_value
            instance.extract_info.return_value = fake_info

            urls = fetch_trending_urls(max_results=1)

        assert urls == [full_url]


# ── download_video tests ────────────────────────────────────────────────


class TestDownloadVideo:
    """Tests for the single-video downloader."""

    def test_successful_download(self, tmp_output: Path) -> None:
        """Simulate a successful download by creating the file inside the mock."""

        def fake_download(urls: list[str]) -> None:
            tmp_output.write_bytes(b"\x00" * 1024)

        with mock.patch("auto_shorts_generator.grabber.yt_dlp.YoutubeDL") as MockYDL:
            instance = MockYDL.return_value.__enter__.return_value
            instance.download.side_effect = fake_download

            result = download_video(
                "https://www.youtube.com/watch?v=abc123",
                output_path=tmp_output,
            )

        assert result.exists()
        assert result.stat().st_size == 1024

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b" / "c" / "video.mp4"

        def fake_download(urls: list[str]) -> None:
            nested.write_bytes(b"\x00" * 512)

        with mock.patch("auto_shorts_generator.grabber.yt_dlp.YoutubeDL") as MockYDL:
            instance = MockYDL.return_value.__enter__.return_value
            instance.download.side_effect = fake_download

            result = download_video(
                "https://www.youtube.com/watch?v=abc123",
                output_path=nested,
            )

        assert result.exists()

    @mock.patch("auto_shorts_generator.grabber.time.sleep")  # don't actually sleep
    def test_retries_on_failure_then_succeeds(
        self, mock_sleep: mock.MagicMock, tmp_output: Path
    ) -> None:
        call_count = 0

        def flaky_download(urls: list[str]) -> None:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise socket.timeout("connection timed out")
            tmp_output.write_bytes(b"\x00" * 256)

        with mock.patch("auto_shorts_generator.grabber.yt_dlp.YoutubeDL") as MockYDL:
            instance = MockYDL.return_value.__enter__.return_value
            instance.download.side_effect = flaky_download

            result = download_video(
                "https://www.youtube.com/watch?v=abc123",
                output_path=tmp_output,
                retries=3,
            )

        assert result.exists()
        assert call_count == 3
        # Verify exponential back-off sleeps were called
        assert mock_sleep.call_count == 2

    @mock.patch("auto_shorts_generator.grabber.time.sleep")
    def test_raises_after_all_retries_exhausted(
        self, mock_sleep: mock.MagicMock, tmp_output: Path
    ) -> None:
        with mock.patch("auto_shorts_generator.grabber.yt_dlp.YoutubeDL") as MockYDL:
            instance = MockYDL.return_value.__enter__.return_value
            instance.download.side_effect = socket.timeout("persistent timeout")

            with pytest.raises(DownloadError, match="All 2 download attempts failed"):
                download_video(
                    "https://www.youtube.com/watch?v=abc123",
                    output_path=tmp_output,
                    retries=2,
                )

    def test_removes_stale_file(self, tmp_output: Path) -> None:
        """An existing file at the output path should be removed before download."""
        tmp_output.write_text("stale data")

        def fake_download(urls: list[str]) -> None:
            tmp_output.write_bytes(b"\x00" * 64)

        with mock.patch("auto_shorts_generator.grabber.yt_dlp.YoutubeDL") as MockYDL:
            instance = MockYDL.return_value.__enter__.return_value
            instance.download.side_effect = fake_download

            result = download_video(
                "https://www.youtube.com/watch?v=abc123",
                output_path=tmp_output,
            )

        assert result.stat().st_size == 64  # stale data replaced


# ── grab() integration-style tests ──────────────────────────────────────


class TestGrab:
    """Tests for the convenience one-call function."""

    def test_grab_wires_fetch_and_download(self, tmp_output: Path) -> None:
        with (
            mock.patch(
                "auto_shorts_generator.grabber.fetch_trending_urls",
                return_value=["https://www.youtube.com/watch?v=top1"],
            ) as mock_fetch,
            mock.patch(
                "auto_shorts_generator.grabber.download_video",
                return_value=tmp_output,
            ) as mock_dl,
        ):
            result = grab(output_path=tmp_output)

        mock_fetch.assert_called_once_with(max_results=1)
        mock_dl.assert_called_once_with(
            "https://www.youtube.com/watch?v=top1",
            output_path=tmp_output,
        )
        assert result == tmp_output

    def test_grab_propagates_fetch_error(self) -> None:
        with mock.patch(
            "auto_shorts_generator.grabber.fetch_trending_urls",
            side_effect=NoTrendingVideosError("no videos"),
        ):
            with pytest.raises(NoTrendingVideosError):
                grab()

    def test_grab_propagates_download_error(self) -> None:
        with (
            mock.patch(
                "auto_shorts_generator.grabber.fetch_trending_urls",
                return_value=["https://www.youtube.com/watch?v=x"],
            ),
            mock.patch(
                "auto_shorts_generator.grabber.download_video",
                side_effect=DownloadError("boom"),
            ),
        ):
            with pytest.raises(DownloadError):
                grab()


# ── Exception hierarchy ─────────────────────────────────────────────────


class TestExceptionHierarchy:
    def test_all_errors_are_grabber_errors(self) -> None:
        assert issubclass(NoTrendingVideosError, GrabberError)
        assert issubclass(DownloadError, GrabberError)

    def test_grabber_error_is_exception(self) -> None:
        assert issubclass(GrabberError, Exception)
