"""OS-appropriate application directories.

Wraps :mod:`platformdirs` so every module resolves the same per-user config,
log and data locations. Centralising this here keeps path logic out of feature
modules and makes it trivial to redirect everything (e.g. in tests) via the
``AI_CASTER_HOME`` environment variable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import PlatformDirs

_APP_NAME = "AIEsportsCaster"
_APP_AUTHOR = "AIEsportsCaster"

#: Environment variable that, when set, overrides all application directories to
#: live under a single root. Primarily used by tests and portable installs.
HOME_ENV_VAR = "AI_CASTER_HOME"


@dataclass(frozen=True)
class AppPaths:
    """Resolved application directories.

    All directories are created on access via :meth:`ensure`.
    """

    config_dir: Path
    data_dir: Path
    log_dir: Path
    cache_dir: Path

    @property
    def settings_file(self) -> Path:
        """Path to the persisted user settings document."""
        return self.config_dir / "settings.json"

    def ensure(self) -> AppPaths:
        """Create every directory if missing and return ``self`` for chaining."""
        for directory in (self.config_dir, self.data_dir, self.log_dir, self.cache_dir):
            directory.mkdir(parents=True, exist_ok=True)
        return self


def get_app_paths(home_override: str | os.PathLike[str] | None = None) -> AppPaths:
    """Resolve application paths.

    Resolution order:

    1. Explicit ``home_override`` argument.
    2. The ``AI_CASTER_HOME`` environment variable.
    3. Platform defaults from :mod:`platformdirs`.
    """
    override = home_override if home_override is not None else os.environ.get(HOME_ENV_VAR)
    if override:
        root = Path(override).expanduser()
        return AppPaths(
            config_dir=root / "config",
            data_dir=root / "data",
            log_dir=root / "logs",
            cache_dir=root / "cache",
        )

    dirs = PlatformDirs(appname=_APP_NAME, appauthor=_APP_AUTHOR, roaming=True)
    return AppPaths(
        config_dir=Path(dirs.user_config_dir),
        data_dir=Path(dirs.user_data_dir),
        log_dir=Path(dirs.user_log_dir),
        cache_dir=Path(dirs.user_cache_dir),
    )
