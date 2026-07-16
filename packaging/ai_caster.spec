# PyInstaller spec for AI Casters (Windows desktop build).
#
# Produces a windowed one-folder build under dist/AICasters/ with the brand icon
# and all packaged data (logo). Inno Setup (installer.iss) then wraps that folder
# into AICasters-Setup.exe.
#
# Build:  pyinstaller packaging/ai_caster.spec --noconfirm
#
# One-folder (not one-file) is deliberate: it starts faster and is friendlier to
# antivirus heuristics than a self-extracting one-file exe — it matters for an
# unattended broadcast box.

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 - SPECPATH injected by PyInstaller
ICON = ROOT / "src" / "ai_caster" / "ui" / "assets" / "logo.ico"

# Ship the package's data files (the logo PNG/ICO, py.typed, and the baked
# deployment defaults). deploy_defaults.json is written by CI before the build
# (from the SUPABASE_* secrets); it MUST be bundled or the frozen app can't read
# its account/updater configuration and sign-in stays disabled.
datas = collect_data_files(
    "ai_caster", includes=["**/*.png", "**/*.ico", "py.typed", "deploy_defaults.json"]
)

# PySide6 + numpy have PyInstaller hooks; make sure optional lazily-imported
# backends that ARE installed on the build box get bundled too. certifi is
# imported lazily (in core.http) so name it explicitly — its PyInstaller hook
# then bundles the CA bundle that HTTPS verification needs.
hiddenimports = collect_submodules("ai_caster") + ["certifi"]

block_cipher = None

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AICasters",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed GUI app
    icon=str(ICON),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="AICasters",
)
