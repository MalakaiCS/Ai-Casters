"""The GPU-aware buffering seam.

"GPU acceleration where available" is honoured as an explicit, injectable step
rather than a fake one. The pipeline passes every frame through a
:class:`FrameUploader` before buffering. The default :class:`CpuUploader` is a
no-op; the Computer Vision milestone (M4) plugs in a real CUDA/torch uploader
that moves pixels to device memory here — without the pipeline changing.

:func:`probe_gpu` reports whether an accelerator is actually present, so startup
diagnostics can log the truth instead of assuming.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ai_caster.capture.frame import Frame
from ai_caster.core.logging import get_logger

_log = get_logger("capture.uploader")


@runtime_checkable
class FrameUploader(Protocol):
    """Prepares a frame for downstream processing (e.g. GPU upload)."""

    @property
    def device(self) -> str: ...

    def upload(self, frame: Frame) -> Frame: ...


class CpuUploader:
    """No-op uploader: frames stay in CPU memory. The default for M1–M3."""

    device = "cpu"

    def upload(self, frame: Frame) -> Frame:
        return frame


def probe_gpu() -> str | None:
    """Return an accelerator name if one is available, else ``None``.

    Best-effort and dependency-free at import time: torch is imported lazily and
    any failure is treated as "no GPU". This never raises.
    """
    try:  # pragma: no cover - depends on optional torch + hardware
        import torch  # type: ignore

        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0)
    except Exception:  # noqa: BLE001 - torch missing or no CUDA is a normal state
        return None
    return None


def create_uploader(use_gpu: bool) -> FrameUploader:
    """Choose an uploader. Falls back to CPU unless a real GPU uploader lands.

    In M3 only :class:`CpuUploader` exists, so this always returns a CPU
    uploader, but it logs whether a GPU *could* be used so operators know their
    hardware is detected ahead of the M4 accelerated path.
    """
    if use_gpu:
        gpu = probe_gpu()
        if gpu:
            _log.info("GPU detected (%s); accelerated upload lands in M4, using CPU for now.", gpu)
        else:
            _log.info("No GPU detected; using CPU frame path.")
    return CpuUploader()
