# -*- coding: utf-8 -*-
"""Audio post-processing: enhancement, normalization, tempo adjustment."""

import os
import logging
import numpy as np
from typing import Optional, Tuple

logger = logging.getLogger("tts_multimodel")


def normalize_loudness(audio: np.ndarray, sample_rate: int = 24000, target_lufs: float = -16.0) -> np.ndarray:
    """Normalize audio to target LUFS (approximated via RMS).
    
    Since we don't have pyloudnorm, we use RMS-based normalization
    as a reasonable approximation for speech content.
    
    Args:
        audio: Input audio array (float32, -1 to 1).
        sample_rate: Sample rate in Hz.
        target_lufs: Target loudness in LUFS (default -16.0 for speech).
    
    Returns:
        Normalized audio array.
    """
    if audio.size == 0:
        return audio

    # Calculate RMS
    rms = np.sqrt(np.mean(audio ** 2))
    if rms < 1e-10:
        return audio  # Silence, skip normalization

    # Current "loudness" approximation (dBFS)
    current_loudness = 20 * np.log10(rms)
    
    # Calculate gain needed
    gain_db = target_lufs - current_loudness
    gain_linear = 10 ** (gain_db / 20.0)
    
    # Apply gain with clipping protection
    normalized = audio * gain_linear
    
    # Soft clipping if needed
    max_val = np.max(np.abs(normalized))
    if max_val > 0.99:
        normalized = normalized / max_val * 0.95
    
    return normalized.astype(np.float32)


def adjust_tempo(audio: np.ndarray, sample_rate: int, factor: float) -> Tuple[np.ndarray, int]:
    """Adjust audio tempo without changing pitch.
    
    Uses simple resampling approach (changes pitch slightly).
    For pitch-preserving tempo change, would need phase vocoder or WSOLA.
    
    Args:
        audio: Input audio array.
        sample_rate: Original sample rate.
        factor: Tempo factor (>1 = faster, <1 = slower).
    
    Returns:
        (adjusted_audio, new_sample_rate)
    """
    if factor <= 0 or factor == 1.0:
        return audio, sample_rate

    # Simple resampling approach
    new_length = int(len(audio) / factor)
    indices = np.linspace(0, len(audio) - 1, new_length).astype(int)
    adjusted = audio[indices]
    
    return adjusted.astype(np.float32), sample_rate


def apply_voice_enhancement(audio: np.ndarray, sample_rate: int = 24000) -> np.ndarray:
    """Apply voice-specific enhancement: gentle EQ + compression.
    
    Args:
        audio: Input audio array.
        sample_rate: Sample rate in Hz.
    
    Returns:
        Enhanced audio array.
    """
    if audio.size == 0:
        return audio

    # Simple high-pass filter to remove rumble (below 80Hz)
    from scipy.signal import butter, lfilter
    
    nyquist = sample_rate / 2.0
    cutoff = 80.0 / nyquist
    b, a = butter(2, cutoff, btype='high', analog=False)
    enhanced = lfilter(b, a, audio)
    
    # Gentle compression
    threshold = 0.3
    ratio = 4.0
    compressed = np.zeros_like(enhanced)
    abs_signal = np.abs(enhanced)
    above_threshold = abs_signal > threshold
    
    compressed[~above_threshold] = enhanced[~above_threshold]
    if np.any(above_threshold):
        gain = threshold + (abs_signal[above_threshold] - threshold) / ratio
        compressed[above_threshold] = np.sign(enhanced[above_threshold]) * gain
    
    # Normalize to -3dB peak
    peak = np.max(np.abs(compressed))
    if peak > 0:
        compressed = compressed / peak * 0.708  # -3dB
    
    return compressed.astype(np.float32)


def enhance_audio(audio: np.ndarray, sample_rate: int,
                  normalize: bool = True,
                  tempo_factor: float = 1.0,
                  voice_enhancement: bool = False,
                  target_lufs: float = -16.0) -> np.ndarray:
    """Apply all post-processing steps in sequence.

    Args:
        audio: Input audio array.
        sample_rate: Sample rate in Hz.
        normalize: Whether to apply loudness normalization.
        tempo_factor: Tempo adjustment factor (1.0 = no change).
        voice_enhancement: Whether to apply voice enhancement (EQ + compression).
        target_lufs: Target loudness in LUFS for normalization (default -16.0).

    Returns:
        Processed audio array.
    """
    result = audio.copy()

    if voice_enhancement:
        result = apply_voice_enhancement(result, sample_rate)

    if normalize:
        result = normalize_loudness(result, sample_rate, target_lufs)

    if tempo_factor != 1.0:
        result, _ = adjust_tempo(result, sample_rate, tempo_factor)

    return result
