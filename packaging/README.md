<p align="center">
  <img src="../src/ai_caster/ui/assets/logo.png" alt="AI Casters" width="220">
</p>

# Packaging — Windows installer (`AICasters-Setup.exe`)

This folder builds the downloadable Windows installer. Native `.exe` files can
only be produced **on Windows** (PyInstaller and Inno Setup do not cross-compile
from Linux/macOS), so the installer is built either on a Windows machine or by the
GitHub Actions Windows runner.

## What's here

| File | Purpose |
|------|---------|
| `launcher.py` | Tiny GUI entry point PyInstaller freezes |
| `ai_caster.spec` | PyInstaller spec → `dist/AICasters/` (windowed, branded icon, bundled assets) |
| `installer.iss` | Inno Setup script → `dist/installer/AICasters-Setup.exe` |
| `build_windows.ps1` | One-command local build on Windows |

## Build on Windows (local)

Prerequisites: Python 3.11+ and [Inno Setup 6](https://jrsoftware.org/isdl.php)
(`ISCC.exe` on `PATH`). Then, from the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

The installer lands at `dist\installer\AICasters-Setup.exe`.

## Build via GitHub Actions (recommended)

Two workflows in `.github/workflows/`:

- **`build-installer.yml`** runs on every push/PR and on manual dispatch. It builds
  the installer on `windows-latest` and uploads **`AICasters-Setup.exe` as a
  downloadable workflow artifact** — so you can grab the `.exe` from the run's
  *Artifacts* section without cutting a release.
- **`release.yml`** runs when you push a tag like `v0.1.0`. It builds the installer
  and publishes a **GitHub Release** with `AICasters-Setup.exe` attached for public
  download.

```bash
# Cut a downloadable release:
git tag v0.1.0
git push origin v0.1.0
```

## Notes

- The build uses a **one-folder** PyInstaller layout (faster start, friendlier to
  antivirus than one-file).
- The installer requests **per-user** install by default (no admin needed);
  `PrivilegesRequiredOverridesAllowed` lets an admin choose all-users.
- Code signing is not configured. Unsigned installers show a SmartScreen warning;
  add a signing step (a `signtool` call after ISCC) once you have a certificate.
