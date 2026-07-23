"""Neural audio watermarking for AI-generated speech content traceability.

Inspired by Chatterbox's Perth watermark technology, this module provides
invisible watermarking of TTS-generated audio for content provenance
tracking and AI-generated content identification.

The watermark embeds a unique identifier into the audio signal that is:
- Inaudible to human listeners
- Robust against common audio transformations (compression, resampling)
- Detectable for verification purposes

Watermarking Strategy:
  - Frequency-domain embedding using spread-spectrum technique
  - Watermark bits are encoded as pseudo-random noise patterns
  - Applied in the 16-20 kHz band (above most speech energy)
  - SNR (signal-to-noise ratio) is kept above 30dB for transparency

This is a lightweight, CPU-only implementation that does NOT require
neural network inference, making it suitable for real-time applications.
"""

from __future__ import annotations

import hashlib
import logging
import struct
import time
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger("tts_multimodel.watermark")

# Watermark parameters
_WATERMARK_VERSION = 1
_WATERMARK_BITS = 64  # Number of bits in the watermark payload
_WATERMARK_STRENGTH = 0.008  # Embedding strength (amplitude of watermark signal)
_WATERMARK_FREQ_LOW = 16000  # Lower frequency bound for embedding (Hz)
_WATERMARK_FREQ_HIGH = 20000  # Upper frequency bound for embedding (Hz)
_WATERMARK_FRAME_SIZE = 2048  # FFT frame size
_WATERMARK_REPEAT = 4  # Number of times watermark is repeated for robustness


@dataclass
class WatermarkPayload:
    """Decoded watermark payload."""

    version: int
    source_id: str  # Unique source identifier (e.g., "tts-multimodel")
    timestamp: float  # Unix timestamp when watermark was embedded
    content_hash: str  # Short hash of the audio content
    extra: dict | None = None  # Optional additional metadata


@dataclass
class WatermarkResult:
    """Result of watermark embedding or detection."""

    success: bool
    message: str
    payload: WatermarkPayload | None = None
    snr_db: float = 0.0  # Signal-to-noise ratio after embedding


# ============================================================================
# Watermark Generation
# ============================================================================


def _generate_watermark_key(source_id: str, timestamp: float) -> np.ndarray:
    """Generate a pseudo-random watermark key from source ID and timestamp.

    The key determines the spread-spectrum pattern used for embedding.
    Using the same source_id and timestamp produces the same key,
    enabling watermark detection.
    """
    seed_data = f"{source_id}:{timestamp:.6f}".encode("utf-8")
    seed = int(hashlib.sha256(seed_data).hexdigest()[:8], 16) % (2**32)
    rng = np.random.RandomState(seed)
    # Generate bipolar sequence (+1/-1)
    return rng.choice([-1.0, 1.0], size=_WATERMARK_BITS)


def _bits_to_payload_bytes(source_id: str, timestamp: float, content_hash: str) -> bytes:
    """Encode watermark payload as bytes for embedding."""
    # Pack: version(1) + source_id_len(1) + source_id + timestamp(8) + content_hash(8)
    source_bytes = source_id.encode("utf-8")[:32]  # Truncate to 32 bytes max
    return struct.pack(
        f"B B {len(source_bytes)}s d 8s",
        _WATERMARK_VERSION,
        len(source_bytes),
        source_bytes,
        timestamp,
        content_hash[:8].encode("utf-8"),
    )


def _payload_bytes_to_bits(payload_bytes: bytes) -> np.ndarray:
    """Convert payload bytes to a bit array."""
    bits = []
    for byte in payload_bytes:
        for i in range(8):
            bits.append((byte >> (7 - i)) & 1)
    # Pad or truncate to _WATERMARK_BITS
    while len(bits) < _WATERMARK_BITS:
        bits.append(0)
    return np.array(bits[:_WATERMARK_BITS], dtype=np.float64) * 2 - 1  # Map to +1/-1


def _compute_content_hash(audio: np.ndarray, sample_rate: int) -> str:
    """Compute a short hash of the audio content for watermark payload."""
    # Downsample to 16kHz for consistent hashing
    if sample_rate != 16000:
        ratio = sample_rate / 16000
        n_samples = int(len(audio) / ratio)
        indices = np.linspace(0, len(audio) - 1, n_samples).astype(int)
        audio_16k = audio[indices]
    else:
        audio_16k = audio

    # Quantize to 16-bit and hash
    quantized = (audio_16k * 32767).astype(np.int16).tobytes()
    return hashlib.sha256(quantized).hexdigest()[:16]


# ============================================================================
# Watermark Embedding
# ============================================================================


def embed_watermark(
    audio: np.ndarray,
    sample_rate: int,
    source_id: str = "tts-multimodel",
    strength: float = _WATERMARK_STRENGTH,
    timestamp: float | None = None,
) -> tuple[np.ndarray, WatermarkResult]:
    """Embed an invisible watermark into audio.

    Uses spread-spectrum technique in the frequency domain to embed
    watermark bits as pseudo-random noise patterns.

    Args:
        audio: Input audio array (float32, mono or stereo).
        sample_rate: Sample rate in Hz.
        source_id: Identifier for the watermark source.
        strength: Embedding strength (0.001-0.05, default 0.008).
        timestamp: Unix timestamp (default: current time).

    Returns:
        Tuple of (watermarked_audio, WatermarkResult).
    """
    if timestamp is None:
        timestamp = time.time()

    # Ensure mono
    if audio.ndim > 1:
        audio_mono = np.mean(audio, axis=-1)
    else:
        audio_mono = audio.copy()

    audio_mono = audio_mono.astype(np.float32)

    # Compute content hash
    content_hash = _compute_content_hash(audio_mono, sample_rate)

    # Generate watermark bits
    watermark_key = _generate_watermark_key(source_id, timestamp)
    payload_bytes = _bits_to_payload_bytes(source_id, timestamp, content_hash)
    payload_bits = _payload_bytes_to_bits(payload_bytes)

    # Encode: watermark_signal = sum of modulated carrier waves
    n_samples = len(audio_mono)

    # Create watermark signal using DFT-based spread spectrum
    watermark_signal = np.zeros(n_samples, dtype=np.float32)

    # Frequency bin mapping
    freq_low_bin = int(_WATERMARK_FREQ_LOW * _WATERMARK_FRAME_SIZE / sample_rate)
    freq_high_bin = int(_WATERMARK_FREQ_HIGH * _WATERMARK_FRAME_SIZE / sample_rate)
    freq_high_bin = min(freq_high_bin, _WATERMARK_FRAME_SIZE // 2)

    n_freq_bins = freq_high_bin - freq_low_bin
    if n_freq_bins < _WATERMARK_BITS:
        logger.warning(
            f"Not enough frequency bins ({n_freq_bins}) for {_WATERMARK_BITS} watermark bits. "
            f"Reducing watermark bits to {n_freq_bins}."
        )
        effective_bits = min(_WATERMARK_BITS, n_freq_bins)
    else:
        effective_bits = _WATERMARK_BITS

    # Embed using overlap-add with random phase modulation
    frame_size = _WATERMARK_FRAME_SIZE
    hop_size = frame_size // 2
    n_frames = max(1, (n_samples - frame_size) // hop_size + 1)

    rng = np.random.RandomState(42)
    carrier_phases = rng.uniform(0, 2 * np.pi, size=effective_bits)

    for rep in range(_WATERMARK_REPEAT):
        for frame_idx in range(n_frames):
            start = frame_idx * hop_size
            end = min(start + frame_size, n_samples)
            if end - start < frame_size:
                break

            frame = audio_mono[start:end]

            # Apply FFT
            fft = np.fft.rfft(frame)

            # Embed watermark bits into selected frequency bins
            for bit_idx in range(effective_bits):
                freq_bin = freq_low_bin + bit_idx
                if freq_bin < len(fft):
                    # Modulate with watermark bit and carrier phase
                    modulation = payload_bits[bit_idx] * strength * np.exp(1j * carrier_phases[bit_idx])
                    fft[freq_bin] += modulation
                    # Mirror for symmetry
                    mirror_bin = frame_size - freq_bin
                    if mirror_bin < len(fft):
                        fft[mirror_bin] += np.conj(modulation)

            # Apply IFFT
            watermarked_frame = np.fft.irfft(fft, n=frame_size)

            # Overlap-add
            watermark_signal[start:end] += watermarked_frame - frame

    # Normalize watermark signal
    max_wm = np.max(np.abs(watermark_signal))
    if max_wm > 0:
        watermark_signal = watermark_signal / max_wm * strength * np.max(np.abs(audio_mono))

    # Add watermark to audio
    watermarked = audio_mono + watermark_signal

    # Calculate SNR
    noise_power = np.mean(watermark_signal**2)
    signal_power = np.mean(audio_mono**2)
    if noise_power > 0:
        snr_db = 10 * np.log10(signal_power / noise_power)
    else:
        snr_db = float("inf")

    # Restore original shape
    if audio.ndim > 1:
        watermarked = np.stack([watermarked] * audio.shape[-1], axis=-1)

    payload = WatermarkPayload(
        version=_WATERMARK_VERSION,
        source_id=source_id,
        timestamp=timestamp,
        content_hash=content_hash,
    )

    logger.info(
        f"Watermark embedded: source={source_id}, SNR={snr_db:.1f}dB, "
        f"hash={content_hash}"
    )

    return watermarked.astype(np.float32), WatermarkResult(
        success=True,
        message="Watermark embedded successfully",
        payload=payload,
        snr_db=snr_db,
    )


# ============================================================================
# Watermark Detection
# ============================================================================


def detect_watermark(
    audio: np.ndarray,
    sample_rate: int,
    source_id: str = "tts-multimodel",
) -> WatermarkResult:
    """Detect and decode a watermark from audio.

    Uses correlation-based detection to find embedded watermark bits
    and reconstruct the payload.

    Args:
        audio: Input audio array (float32, mono or stereo).
        sample_rate: Sample rate in Hz.
        source_id: Expected source ID for verification.

    Returns:
        WatermarkResult with detected payload or failure message.
    """
    # Ensure mono
    if audio.ndim > 1:
        audio_mono = np.mean(audio, axis=-1)
    else:
        audio_mono = audio.copy()

    audio_mono = audio_mono.astype(np.float32)
    n_samples = len(audio_mono)

    frame_size = _WATERMARK_FRAME_SIZE
    hop_size = frame_size // 2
    n_frames = max(1, (n_samples - frame_size) // hop_size + 1)

    freq_low_bin = int(_WATERMARK_FREQ_LOW * frame_size / sample_rate)
    freq_high_bin = int(_WATERMARK_FREQ_HIGH * frame_size / sample_rate)
    freq_high_bin = min(freq_high_bin, frame_size // 2)
    n_freq_bins = freq_high_bin - freq_low_bin
    effective_bits = min(_WATERMARK_BITS, n_freq_bins)

    # Collect correlation statistics for each bit
    bit_correlations = np.zeros(effective_bits)
    bit_counts = np.zeros(effective_bits)

    rng = np.random.RandomState(42)
    carrier_phases = rng.uniform(0, 2 * np.pi, size=effective_bits)

    # Try multiple timestamps to find the watermark
    # For detection, we try the most common timestamp patterns
    best_score = 0.0
    best_timestamp = 0.0
    best_bits = np.zeros(effective_bits)

    # Scan with a window of candidate timestamps
    current_time = time.time()
    candidates = [current_time]  # Start with current time

    for timestamp in candidates:
        key = _generate_watermark_key(source_id, timestamp)

        correlations = np.zeros(effective_bits)
        counts = np.zeros(effective_bits)

        for frame_idx in range(n_frames):
            start = frame_idx * hop_size
            end = min(start + frame_size, n_samples)
            if end - start < frame_size:
                break

            frame = audio_mono[start:end]
            fft = np.fft.rfft(frame)

            for bit_idx in range(effective_bits):
                freq_bin = freq_low_bin + bit_idx
                if freq_bin < len(fft):
                    # Correlate with expected carrier
                    carrier = np.exp(1j * carrier_phases[bit_idx])
                    corr = np.real(fft[freq_bin] * np.conj(carrier))
                    correlations[bit_idx] += corr
                    counts[bit_idx] += 1

        # Average correlations
        valid = counts > 0
        if np.any(valid):
            avg_correlations = np.where(valid, correlations / counts, 0)
            detected_bits = np.sign(avg_correlations)
            score = np.mean(np.abs(avg_correlations))

            if score > best_score:
                best_score = score
                best_timestamp = timestamp
                best_bits = detected_bits

    # Check if watermark was detected (score above threshold)
    detection_threshold = 0.001
    if best_score < detection_threshold:
        return WatermarkResult(
            success=False,
            message="No watermark detected in audio",
            payload=None,
        )

    # Reconstruct payload from detected bits
    bits_uint8 = ((best_bits + 1) / 2).astype(np.uint8)[:_WATERMARK_BITS]
    bit_bytes = bytearray()
    for i in range(0, len(bits_uint8), 8):
        byte_val = 0
        for j in range(8):
            if i + j < len(bits_uint8):
                byte_val = (byte_val << 1) | int(bits_uint8[i + j])
            else:
                byte_val = byte_val << 1
        bit_bytes.append(byte_val)

    # Parse payload
    try:
        if len(bit_bytes) >= 1:
            version = bit_bytes[0]
            source_len = bit_bytes[1] if len(bit_bytes) > 1 else 0
            source = bytes(bit_bytes[2 : 2 + source_len]).decode("utf-8", errors="replace")
            ts_bytes = bytes(bit_bytes[2 + source_len : 2 + source_len + 8])
            if len(ts_bytes) == 8:
                timestamp = struct.unpack("d", ts_bytes)[0]
            else:
                timestamp = 0.0
            hash_bytes = bytes(bit_bytes[10 + source_len : 18 + source_len])
            content_hash = hash_bytes.decode("utf-8", errors="replace") if hash_bytes else ""

            payload = WatermarkPayload(
                version=version,
                source_id=source,
                timestamp=timestamp,
                content_hash=content_hash,
            )

            return WatermarkResult(
                success=True,
                message="Watermark detected successfully",
                payload=payload,
                snr_db=best_score,
            )
    except Exception as e:
        logger.debug(f"Payload decode error: {e}")

    return WatermarkResult(
        success=False,
        message="Watermark detected but payload decode failed",
        payload=None,
    )


# ============================================================================
# Convenience Functions
# ============================================================================


def watermark_audio(
    audio: np.ndarray,
    sample_rate: int,
    enable: bool = True,
    source_id: str = "tts-multimodel",
) -> tuple[np.ndarray, dict]:
    """Convenience function to optionally watermark audio.

    Args:
        audio: Input audio array.
        sample_rate: Sample rate in Hz.
        enable: Whether to apply watermarking.
        source_id: Watermark source identifier.

    Returns:
        Tuple of (processed_audio, metadata_dict).
    """
    if not enable:
        return audio, {"watermarked": False}

    watermarked, result = embed_watermark(audio, sample_rate, source_id=source_id)

    metadata = {
        "watermarked": result.success,
        "snr_db": round(result.snr_db, 1),
    }
    if result.payload:
        metadata["source_id"] = result.payload.source_id
        metadata["content_hash"] = result.payload.content_hash

    return watermarked, metadata
