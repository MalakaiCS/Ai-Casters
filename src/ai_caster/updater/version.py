"""A small semantic-version type for update comparisons.

Only what the updater needs: parse ``MAJOR.MINOR.PATCH`` (with an optional
pre-release suffix that sorts *below* the same release), compare, and format.
Kept dependency-free rather than pulling in ``packaging``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import total_ordering

_PATTERN = re.compile(r"^\s*v?(\d+)\.(\d+)\.(\d+)(?:[-+]([0-9A-Za-z.\-]+))?\s*$")


@total_ordering
@dataclass(frozen=True)
class Version:
    """A parsed semantic version. Pre-release builds sort below their release."""

    major: int
    minor: int
    patch: int
    prerelease: str = ""

    @classmethod
    def parse(cls, text: str) -> Version:
        match = _PATTERN.match(text)
        if not match:
            raise ValueError(f"Not a valid version: {text!r}")
        major, minor, patch, pre = match.groups()
        return cls(int(major), int(minor), int(patch), pre or "")

    @property
    def release(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def _key(self) -> tuple:
        # A release outranks any pre-release of the same numbers: encode "no
        # prerelease" as a marker that sorts above any prerelease string.
        return (self.release, 1 if not self.prerelease else 0, self.prerelease)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() == other._key()

    def __lt__(self, other: Version) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() < other._key()

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{self.prerelease}" if self.prerelease else base
