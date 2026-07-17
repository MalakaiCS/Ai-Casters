"""Audio buffer and the per-channel DSP chain.

All DSP is pure NumPy on a mono ``float32`` buffer in ``[-1, 1]`` — no audio
hardware — so it is fully unit-testable. Each voice channel owns an independent
:class:`ChannelDSP` (volume, mute, compressor, 3-band EQ, limiter), matching the
spec's requirement that every voice have its own dynamics processing.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AudioClip:
    """A mono audio buffer with its sample rate."""

    samples: np.ndarray  # float32, shape (N,), nominally in [-1, 1]
    sample_rate: int

    @property
    def duration(self) -> float:
        return len(self.samples) / self.sample_rate if self.sample_rate else 0.0

    @property
    def peak(self) -> float:
        return float(np.max(np.abs(self.samples))) if self.samples.size else 0.0

    def with_samples(self, samples: np.ndarray) -> AudioClip:
        return AudioClip(samples=samples.astype(np.float32), sample_rate=self.sample_rate)


# --------------------------------------------------------------------------- #
# DSP primitives (pure functions)
# --------------------------------------------------------------------------- #
def apply_gain(samples: np.ndarray, gain: float) -> np.ndarray:
    return (samples * gain).astype(np.float32)


def compress(samples: np.ndarray, *, threshold: float, ratio: float) -> np.ndarray:
    """Static (instantaneous) downward compressor.

    Samples whose magnitude exceeds ``threshold`` are pushed toward the threshold
    by ``ratio`` (peaks above the threshold are reduced by ``1/ratio``). Simple
    and predictable — good enough to tame broadcast dynamics and easy to test.
    """
    if ratio <= 1.0:
        return samples.astype(np.float32)
    mag = np.abs(samples)
    over = mag > threshold
    compressed = np.where(
        over,
        np.sign(samples) * (threshold + (mag - threshold) / ratio),
        samples,
    )
    return compressed.astype(np.float32)


def _one_pole_lowpass(samples: np.ndarray, alpha: float) -> np.ndarray:
    """Simple exponential-smoothing low-pass. ``alpha`` in (0, 1]; smaller = more
    low-pass."""
    if samples.size == 0:
        return samples.astype(np.float32)
    out = np.empty_like(samples, dtype=np.float32)
    acc = 0.0
    for i in range(samples.size):
        acc += alpha * (samples[i] - acc)
        out[i] = acc
    return out


def three_band_eq(
    samples: np.ndarray, *, low_gain: float, mid_gain: float, high_gain: float
) -> np.ndarray:
    """Split into low/mid/high bands and recombine with per-band gains.

    Bands are separated with two one-pole low-passes. With all gains at 1.0 the
    output reconstructs the input (the three bands sum to the original signal).
    """
    if samples.size == 0 or (low_gain == mid_gain == high_gain == 1.0):
        return samples.astype(np.float32)
    low = _one_pole_lowpass(samples, 0.05)
    low_mid = _one_pole_lowpass(samples, 0.35)
    mid = low_mid - low
    high = samples - low_mid
    out = low * low_gain + mid * mid_gain + high * high_gain
    return out.astype(np.float32)


def limit(samples: np.ndarray, ceiling: float) -> np.ndarray:
    """Hard peak limiter: clamp magnitude to ``ceiling``."""
    return np.clip(samples, -ceiling, ceiling).astype(np.float32)


# --------------------------------------------------------------------------- #
# Per-channel chain
# --------------------------------------------------------------------------- #
@dataclass
class ChannelDSP:
    """A channel's independent volume/mute/compressor/EQ/limiter chain."""

    volume: float = 1.0
    muted: bool = False
    compressor_enabled: bool = True
    compressor_threshold: float = 0.5
    compressor_ratio: float = 3.0
    eq_low: float = 1.0
    eq_mid: float = 1.0
    eq_high: float = 1.0
    limiter_ceiling: float = 0.95

    def process(self, clip: AudioClip) -> AudioClip:
        """Apply the full chain: mute → volume → compressor → EQ → limiter."""
        if self.muted or self.volume <= 0.0:
            return clip.with_samples(np.zeros_like(clip.samples))
        samples = apply_gain(clip.samples, self.volume)
        if self.compressor_enabled:
            samples = compress(
                samples, threshold=self.compressor_threshold, ratio=self.compressor_ratio
            )
        samples = three_band_eq(
            samples, low_gain=self.eq_low, mid_gain=self.eq_mid, high_gain=self.eq_high
        )
        samples = limit(samples, self.limiter_ceiling)
        return clip.with_samples(samples)


def mix(clips: list[AudioClip], *, gain: float = 1.0, ceiling: float = 0.99) -> AudioClip:
    """Sum several clips (zero-padded to the longest) into one, limited.

    Used for the combined monitor mix. Clips must share a sample rate.
    """
    clips = [c for c in clips if c.samples.size]
    if not clips:
        return AudioClip(np.zeros(0, dtype=np.float32), sample_rate=24000)
    sample_rate = clips[0].sample_rate
    length = max(c.samples.size for c in clips)
    acc = np.zeros(length, dtype=np.float32)
    for clip in clips:
        acc[: clip.samples.size] += clip.samples
    acc = limit(apply_gain(acc, gain), ceiling)
    return AudioClip(acc, sample_rate=sample_rate)
