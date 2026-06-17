"""全应用共享状态：唯一 SSH 连接 + profile 存储 + 连接状态信号。

各面板拿同一个 AppContext，连接/断开时通过信号刷新自己。
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from core.profiles import Profile, ProfileStore
from core.ssh_client import SSHClient


class AppContext(QObject):
    connected = pyqtSignal(object)     # 发 Profile
    disconnected = pyqtSignal()
    status_message = pyqtSignal(str)   # 状态栏文本

    def __init__(self) -> None:
        super().__init__()
        self.store = ProfileStore()
        self.ssh = SSHClient()
        self.profile: Optional[Profile] = None

    @property
    def is_connected(self) -> bool:
        return self.ssh.is_alive()

    def set_connected(self, profile: Profile) -> None:
        self.profile = profile
        self.connected.emit(profile)
        self.status_message.emit(f"已连接 {profile.username}@{profile.host}")

    def set_disconnected(self) -> None:
        try:
            self.ssh.close()
        except Exception:
            pass
        self.profile = None
        self.disconnected.emit()
        self.status_message.emit("已断开")
