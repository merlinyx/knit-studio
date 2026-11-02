# PyInstaller spec for Knit Studio. Build from the repository root:
#   pyinstaller packaging/knit-studio.spec --noconfirm
# macOS produces dist/Knit Studio.app; Windows produces dist/Knit Studio.exe.
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = SPECPATH  # noqa: F821 - defined by PyInstaller
NAME = "Knit Studio"
VERSION = open(f"{ROOT}/../src/spacer_pipeline/__init__.py").read().split('__version__ = "')[1].split('"')[0]

a = Analysis(  # noqa: F821
    [f"{ROOT}/launch.py"],
    pathex=[f"{ROOT}/../src"],
    datas=collect_data_files("spacer_pipeline"),
    hiddenimports=collect_submodules("spacer_pipeline"),
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)  # noqa: F821

if sys.platform == "darwin":
    exe = EXE(  # noqa: F821
        pyz, a.scripts, [], exclude_binaries=True, name=NAME,
        console=False, icon=f"{ROOT}/icon.icns",
    )
    collected = COLLECT(exe, a.binaries, a.datas, name=NAME)  # noqa: F821
    app = BUNDLE(  # noqa: F821
        collected,
        name=f"{NAME}.app",
        icon=f"{ROOT}/icon.icns",
        bundle_identifier="edu.washington.cs.knitstudio",
        version=VERSION,
        info_plist={"NSHighResolutionCapable": True, "CFBundleShortVersionString": VERSION},
    )
else:
    exe = EXE(  # noqa: F821
        pyz, a.scripts, a.binaries, a.datas, [], name=NAME,
        console=False, icon=f"{ROOT}/icon.ico",
    )
