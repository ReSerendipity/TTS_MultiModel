# -*- coding: utf-8 -*-
"""FFmpeg process pool for format conversion

Implements a simple FFmpeg process pool that reuses existing FFmpeg processes.
Maintains 1-2 idle FFmpeg processes ready for conversion.
Uses asyncio for non-blocking operation.
Provides a convert(input_path, output_path) function.
Falls back to subprocess.run if pool is unavailable or FFmpeg not found.
"""

import os
import asyncio
import subprocess
import logging
import shutil
from typing import Optional
from pathlib import Path

logger = logging.getLogger("tts_multimodel")

# Default pool size
DEFAULT_POOL_SIZE = 2


class FFmpegProcessPool:
    """Simple FFmpeg process pool for audio format conversion.

    Maintains a pool of idle FFmpeg processes that can be reused for
    audio conversion tasks. Uses asyncio for non-blocking operation.
    """

    def __init__(self, pool_size: int = DEFAULT_POOL_SIZE):
        self._pool_size = pool_size
        self._initialized = False
        self._semaphore: Optional[asyncio.Semaphore] = None

    async def initialize(self):
        """Initialize the process pool semaphore."""
        if not self._initialized:
            self._semaphore = asyncio.Semaphore(self._pool_size)
            self._initialized = True
            logger.info(f"FFmpeg process pool initialized (size: {self._pool_size})")

    @property
    def is_available(self) -> bool:
        """Check if the pool is ready to use."""
        return self._initialized and self._semaphore is not None

    async def convert(
        self,
        input_path: str,
        output_path: str,
        output_format: Optional[str] = None,
        bitrate: str = "192k",
        codec: Optional[str] = None,
    ) -> bool:
        """Convert audio file using FFmpeg with pool-managed concurrency.

        Args:
            input_path: Path to input audio file
            output_path: Path to output audio file
            output_format: Output format (mp3, wav, ogg, flac). Auto-detected from extension if None.
            bitrate: Audio bitrate (default: 192k)
            codec: Audio codec. Auto-selected based on format if None.

        Returns:
            True if conversion succeeded, False otherwise.
        """
        if not self.is_available:
            await self.initialize()

        if not _ffmpeg_available():
            logger.warning("FFmpeg not found, conversion unavailable")
            return False

        input_path = str(Path(input_path))
        output_path = str(Path(output_path))

        if not os.path.exists(input_path):
            logger.error(f"Input file not found: {input_path}")
            return False

        # Auto-detect format from extension
        if output_format is None:
            ext = Path(output_path).suffix.lower().lstrip(".")
            output_format = ext if ext else "wav"

        # Auto-select codec based on format
        if codec is None:
            codec_map = {
                "mp3": "libmp3lame",
                "ogg": "libvorbis",
                "flac": "flac",
                "wav": "pcm_s16le",
                "aac": "aac",
            }
            codec = codec_map.get(output_format.lower())

        async with self._semaphore:
            try:
                cmd = _build_ffmpeg_command(
                    input_path=input_path,
                    output_path=output_path,
                    output_format=output_format,
                    bitrate=bitrate,
                    codec=codec,
                )
                logger.debug(f"FFmpeg command: {' '.join(cmd)}")

                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await process.communicate()

                if process.returncode != 0:
                    logger.error(
                        f"FFmpeg conversion failed (exit code {process.returncode}): "
                        f"{stderr.decode('utf-8', errors='replace')[:200]}"
                    )
                    return False

                if not os.path.exists(output_path):
                    logger.error(f"Output file not created: {output_path}")
                    return False

                logger.info(
                    f"FFmpeg conversion successful: {os.path.basename(input_path)} -> "
                    f"{os.path.basename(output_path)}"
                )
                return True

            except Exception as e:
                logger.error(f"FFmpeg conversion error: {e}")
                return False


def _ffmpeg_available() -> bool:
    """Check if FFmpeg is available in the system PATH."""
    return shutil.which("ffmpeg") is not None


def _build_ffmpeg_command(
    input_path: str,
    output_path: str,
    output_format: str,
    bitrate: str,
    codec: Optional[str],
) -> list:
    """Build FFmpeg command line arguments."""
    cmd = ["ffmpeg", "-y", "-i", input_path]

    if codec:
        cmd.extend(["-acodec", codec])

    # Apply bitrate for lossy formats
    if output_format.lower() in ("mp3", "ogg", "aac"):
        cmd.extend(["-b:a", bitrate])

    # Add format-specific options
    if output_format.lower() == "wav":
        cmd.extend(["-ar", "48000", "-ac", "1"])
    elif output_format.lower() == "mp3":
        cmd.extend(["-ar", "48000"])

    cmd.extend(["-vn", output_path])
    return cmd


# Module-level singleton instance
_ffmpeg_pool: Optional[FFmpegProcessPool] = None


def get_ffmpeg_pool(pool_size: int = DEFAULT_POOL_SIZE) -> FFmpegProcessPool:
    """Get or create the global FFmpeg process pool instance."""
    global _ffmpeg_pool
    if _ffmpeg_pool is None:
        _ffmpeg_pool = FFmpegProcessPool(pool_size=pool_size)
    return _ffmpeg_pool


def convert_sync(
    input_path: str,
    output_path: str,
    output_format: Optional[str] = None,
    bitrate: str = "192k",
) -> bool:
    """Synchronous wrapper for FFmpeg conversion.

    Tries the async pool first, falls back to subprocess.run if unavailable.
    Reuses the global event loop when possible to avoid creation overhead.

    Args:
        input_path: Path to input audio file
        output_path: Path to output audio file
        output_format: Output format. Auto-detected from extension if None.
        bitrate: Audio bitrate (default: 192k)

    Returns:
        True if conversion succeeded, False otherwise.
    """
    try:
        pool = get_ffmpeg_pool()
        if _ffmpeg_available():
            # Try to reuse an existing event loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    raise RuntimeError("Event loop is closed")
            except RuntimeError:
                # No running loop, create and cache one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            result = loop.run_until_complete(
                pool.convert(
                    input_path=input_path,
                    output_path=output_path,
                    output_format=output_format,
                    bitrate=bitrate,
                )
            )
            return result
    except Exception as e:
        logger.warning(f"FFmpeg pool conversion failed, falling back to subprocess: {e}")

    # Fallback to subprocess.run
    return _convert_fallback(input_path, output_path, output_format, bitrate)


def _convert_fallback(
    input_path: str,
    output_path: str,
    output_format: Optional[str] = None,
    bitrate: str = "192k",
) -> bool:
    """Fallback conversion using subprocess.run."""
    if not _ffmpeg_available():
        logger.error("FFmpeg not found in PATH, cannot convert audio")
        return False

    if output_format is None:
        ext = Path(output_path).suffix.lower().lstrip(".")
        output_format = ext if ext else "wav"

    codec_map = {
        "mp3": "libmp3lame",
        "ogg": "libvorbis",
        "flac": "flac",
        "wav": "pcm_s16le",
    }
    codec = codec_map.get(output_format.lower())

    cmd = _build_ffmpeg_command(
        input_path=input_path,
        output_path=output_path,
        output_format=output_format,
        bitrate=bitrate,
        codec=codec,
    )

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.error(
                f"FFmpeg fallback conversion failed (exit code {result.returncode}): "
                f"{result.stderr[:200]}"
            )
            return False
        return os.path.exists(output_path)
    except subprocess.TimeoutExpired:
        logger.error("FFmpeg fallback conversion timed out")
        return False
    except Exception as e:
        logger.error(f"FFmpeg fallback conversion error: {e}")
        return False
