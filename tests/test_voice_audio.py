"""Tests for the audio buffer and DSP chain (pure NumPy, no hardware)."""

from __future__ import annotations

import numpy as np

from ai_caster.voice.audio import (
    AudioClip,
    ChannelDSP,
    apply_gain,
    compress,
    limit,
    mix,
    three_band_eq,
)


def _clip(samples, rate: int = 24000) -> AudioClip:
    return AudioClip(np.asarray(samples, dtype=np.float32), rate)


def test_clip_duration_and_peak():
    clip = _clip([0.0, 0.5, -0.8, 0.2], rate=4)
    assert clip.duration == 1.0
    assert np.isclose(clip.peak, 0.8)


def test_apply_gain_scales_samples():
    out = apply_gain(np.array([0.5, -0.25], dtype=np.float32), 2.0)
    assert np.allclose(out, [1.0, -0.5])


def test_compress_reduces_peaks_above_threshold_only():
    samples = np.array([0.2, 0.5, 1.0, -1.0], dtype=np.float32)
    out = compress(samples, threshold=0.5, ratio=2.0)
    # Below/at threshold untouched.
    assert out[0] == 0.2
    assert out[1] == 0.5
    # 1.0 -> 0.5 + (1.0 - 0.5)/2 = 0.75, sign preserved.
    assert np.isclose(out[2], 0.75)
    assert np.isclose(out[3], -0.75)


def test_compress_noop_when_ratio_one():
    samples = np.array([0.9, -0.9], dtype=np.float32)
    assert np.allclose(compress(samples, threshold=0.1, ratio=1.0), samples)


def test_three_band_eq_is_identity_at_unity_gain():
    rng = np.random.default_rng(0)
    samples = rng.standard_normal(256).astype(np.float32)
    out = three_band_eq(samples, low_gain=1.0, mid_gain=1.0, high_gain=1.0)
    assert np.allclose(out, samples)


def test_three_band_eq_bands_sum_to_input():
    rng = np.random.default_rng(1)
    samples = rng.standard_normal(512).astype(np.float32)
    # Boosting all bands equally scales the signal (bands partition the input).
    out = three_band_eq(samples, low_gain=2.0, mid_gain=2.0, high_gain=2.0)
    assert np.allclose(out, samples * 2.0, atol=1e-5)


def test_limit_clamps_to_ceiling():
    samples = np.array([1.5, -1.5, 0.3], dtype=np.float32)
    out = limit(samples, 0.9)
    assert out.max() <= 0.9 and out.min() >= -0.9
    assert out[2] == np.float32(0.3)


def test_channel_dsp_mute_zeros_output():
    dsp = ChannelDSP(muted=True)
    out = dsp.process(_clip([0.5, 0.5]))
    assert np.all(out.samples == 0.0)


def test_channel_dsp_volume_and_limiter():
    dsp = ChannelDSP(volume=0.5, compressor_enabled=False, limiter_ceiling=0.95)
    out = dsp.process(_clip([1.0, -1.0]))
    assert np.allclose(out.samples, [0.5, -0.5])


def test_channel_dsp_limiter_caps_loud_signal():
    dsp = ChannelDSP(volume=2.0, compressor_enabled=False, limiter_ceiling=0.9)
    out = dsp.process(_clip([1.0]))
    assert out.peak <= 0.9


def test_mix_sums_and_zero_pads():
    a = _clip([0.2, 0.2, 0.2])
    b = _clip([0.1])
    out = mix([a, b], gain=1.0, ceiling=0.99)
    assert out.samples.size == 3
    assert np.isclose(out.samples[0], 0.3)
    assert np.isclose(out.samples[1], 0.2)


def test_mix_empty_returns_silence():
    out = mix([])
    assert out.samples.size == 0
