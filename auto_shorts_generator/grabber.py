"""
grabber.py – Phase 1: Trending-Video Downloader
================================================
"""

from __future__ import annotations

import socket
import time
from pathlib import Path
from typing import Optional

import yt_dlp

from auto_shorts_generator import config
from auto_shorts_generator.logger import get_logger

log = get_logger(__name__)

class GrabberError(Exception):
    pass

class NoTrendingVideosError(GrabberError):
    pass

class DownloadError(GrabberError):
    pass


def _build_extract_opts() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "socket_timeout": config.DOWNLOAD_TIMEOUT_SEC,
        "playlistend": 15, # Fetch 15 so we can skip live streams
        "extractor_args": {"youtube": ["player_client=ios,web"]} # The iOS bypass
    }


def _build_download_opts(output_path: Path) -> dict:
    return {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "outtmpl": str(output_path),
        "socket_timeout": config.DOWNLOAD_TIMEOUT_SEC,
        "retries": config.DOWNLOAD_RETRIES,
        "fragment_retries": config.DOWNLOAD_RETRIES,
        "quiet": False,
        "no_warnings": False,
        "noprogress": False,
        "fixup": "detect_or_warn",
        "extractor_args": {"youtube": ["player_client=ios,web"]}, # The iOS bypass
        "source_address": "0.0.0.0", # Force IPv4 to avoid CDN blocks
    }


def fetch_trending_urls(max_results: int = 1) -> list[str]:
    log.info("Fetching trending video URLs...")

    opts = _build_extract_opts()
    target_url = getattr(config, "TRENDING_URL", "https://www.youtube.com/feed/trending")
    info = None

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(target_url, download=False)
    except (yt_dlp.utils.DownloadError, socket.timeout, OSError) as exc:
        log.warning("Primary trending URL failed (%s).", exc)

    if not info or not info.get("entries"):
        log.info("Initiating fallback: Using ytsearch...")
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info("ytsearch15:trending videos this week", download=False)
        except Exception as fallback_exc:
            raise NoTrendingVideosError(f"Both primary URL and fallback failed: {fallback_exc}") from fallback_exc

    entries = info.get("entries") or []
    urls: list[str] = []
    
    for entry in entries:
        title = entry.get("title", "Unknown Title")
        is_live = entry.get("is_live") or entry.get("live_status") == "is_live"
        is_upcoming = entry.get("live_status") == "is_upcoming"
        duration = entry.get("duration") or 0
        
        # Skip live streams and long videos
        if is_live or is_upcoming:
            log.info("⏭️  Skipping '%s' (Reason: Live Stream)", title)
            continue
        if duration > 3600:
            log.info("⏭️  Skipping '%s' (Reason: Too long, %ds)", title, duration)
            continue

        video_id = entry.get("id") or entry.get("url")
        if video_id:
            url = video_id if video_id.startswith("http") else f"https://www.youtube.com/watch?v={video_id}"
            urls.append(url)
            
        if len(urls) >= max_results:
            break

    if not urls:
        raise NoTrendingVideosError("Trending page parsed but contained no usable video entries.")

    log.info("Found %d trending URL(s): %s", len(urls), urls)
    return urls


def download_video(url: str, output_path: Optional[Path] = None, *, retries: int = config.DOWNLOAD_RETRIES) -> Path:
    if output_path is None:
        output_path = config.RAW_VIDEO_PATH

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists():
        output_path.unlink()

    opts = _build_download_opts(output_path)
    last_exc: Exception | None = None

    for attempt in range(1, retries + 1):
        log.info("Download attempt %d/%d for %s → %s", attempt, retries, url, output_path)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])

            if output_path.exists():
                log.info("✅  Download complete: %s", output_path.name)
                return output_path.resolve()

            candidates = list(output_path.parent.glob(f"{output_path.stem}*"))
            if candidates:
                actual = candidates[0]
                actual.rename(output_path)
                return output_path.resolve()

            raise FileNotFoundError("yt-dlp reported success but file is missing.")

        except Exception as exc:
            last_exc = exc
            wait = 2**attempt
            log.warning("Attempt %d failed (%s). Retrying in %ds …", attempt, exc, wait)
            time.sleep(wait)

    raise DownloadError(f"All {retries} download attempts failed for {url}") from last_exc


def grab(*, output_path: Optional[Path] = None) -> Path:
    urls = fetch_trending_urls(max_results=1)
    return download_video(urls[0], output_path=output_path)

if __name__ == "__main__":
    import sys
    try:
        path = grab()
        print(f"\n🎬  Saved trending video → {path}")
    except GrabberError as err:
        print(f"\n❌  Grabber failed: {err}", file=sys.stderr)
        sys.exit(1)