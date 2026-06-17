# PyInstaller 打包配置 —— 跨平台单文件。
#   Windows : pyinstaller build.spec --noconfirm  -> dist/HPC-Companion.exe
#   macOS   : pyinstaller build.spec --noconfirm  -> dist/HPC Companion.app
#   Linux   : pyinstaller build.spec --noconfirm  -> dist/HPC-Companion
import sys

from PyInstaller.utils.hooks import collect_submodules

# paramiko / keyring 有动态导入，需显式收集，否则打包后运行时缺模块
hiddenimports = []
hiddenimports += collect_submodules("paramiko")
hiddenimports += collect_submodules("keyring")
hiddenimports += ["pyqtgraph", "cryptography"]

# 凭据库后端按平台收（装错平台的后端会徒增体积 / 报缺依赖）
if sys.platform == "win32":
    hiddenimports += ["keyring.backends.Windows", "win32ctypes.core"]
elif sys.platform == "darwin":
    hiddenimports += ["keyring.backends.macOS"]
else:
    hiddenimports += ["keyring.backends.SecretService"]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    # 关 OpenSSL legacy provider，修打包后 cryptography fatal 崩溃
    runtime_hooks=["rthook_openssl.py"],
    # 排除用不到的重依赖瘦身（pyqtgraph 基础画图不需要 scipy；平滑是纯 python）
    excludes=["matplotlib", "tkinter", "PyQt5", "PySide6", "PySide2",
              "scipy", "pandas", "IPython", "PyQt6.Qt3DCore", "PyQt6.QtWebEngineCore"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="HPC-Companion",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=(sys.platform == "win32"),   # upx 在 macOS 易破坏签名/Gatekeeper，仅 Windows 用
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                   # 无黑窗 / 无终端
    icon=None,                       # 有图标时：Windows 填 .ico，macOS 填 .icns
)

# macOS：把可执行包装成 .app（Finder 双击、Dock 图标、Retina）
if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="HPC Companion.app",
        icon=None,                   # 有图标时填 "assets/app.icns"
        bundle_identifier="io.github.legacccy.hpccompanion",
        info_plist={
            "NSHighResolutionCapable": True,   # Retina 清晰
            "LSMinimumSystemVersion": "11.0",
            "CFBundleShortVersionString": "0.1.0",
            "NSRequiresAquaSystemAppearance": False,  # 跟随系统深 / 浅色
        },
    )
