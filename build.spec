# PyInstaller 打包配置 —— 单文件 exe。
# 构建: pyinstaller build.spec --noconfirm
# 产物: dist/HPC-Companion.exe
from PyInstaller.utils.hooks import collect_submodules

# paramiko / keyring 有动态导入，需显式收集，否则打包后运行时缺模块
hiddenimports = []
hiddenimports += collect_submodules("paramiko")
hiddenimports += collect_submodules("keyring")
hiddenimports += [
    "keyring.backends.Windows",      # Windows 凭据管理器后端
    "keyring.backends.macOS",
    "keyring.backends.SecretService",
    "win32ctypes.core",              # keyring Windows 后端依赖
    "pyqtgraph",
    "cryptography",
]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    # 关 OpenSSL legacy provider，修打包后 cryptography fatal 崩溃
    runtime_hooks=["rthook_openssl.py"],
    # 排除用不到的重依赖，瘦身 exe（pyqtgraph 基础画图不需要 scipy；平滑是纯 python）
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
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # 无黑窗
    icon=None,              # 有图标时填 "assets/app.ico"
)
