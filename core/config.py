"""应用级路径、常量与内置集群预设。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "HPC Companion"
APP_VERSION = "0.1.0"
ORG = "HPCCompanion"

# keyring 服务名（密码加密存于系统凭据库）
KEYRING_SERVICE = "hpc-companion"


def app_data_dir() -> Path:
    """跨平台用户配置目录。Windows: %APPDATA%\\HPC Companion。"""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def profiles_path() -> Path:
    return app_data_dir() / "profiles.json"


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def load_settings() -> dict:
    import json
    p = settings_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_settings(data: dict) -> None:
    import json
    settings_path().write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def resource_path(rel: str) -> Path:
    """打包(PyInstaller)后资源定位。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / rel
    return Path(__file__).resolve().parent.parent / rel


# 内置预设：用户新建连接时可一键套用，凭证仍需自己填。
CLUSTER_PRESETS = {
    "GPU 集群示例": {
        "host": "",                   # 填你的集群登录 / 数据传输节点地址
        "port": 22,
        "username": "",
        "slurm_account": "",          # 填你自己的 SLURM account / 课题组配额
        "partition": "gpu",
        "qos": "gpu",
        "default_remote_dir": "",     # 例 /home/<user>/work
        "vpn_note": "校外通常需先连学校 VPN 才能访问集群。",
        "python_path": "",
    },
    "自定义 / 通用 SLURM 集群": {
        "host": "",
        "port": 22,
        "username": "",
        "slurm_account": "",
        "partition": "",
        "qos": "",
        "default_remote_dir": "",
        "vpn_note": "",
        "python_path": "",
    },
}
