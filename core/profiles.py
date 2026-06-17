"""集群连接 profile 管理。

设计原则（安全红线）：
- 绝不把密码明文写进 profiles.json。
- 密码统一存系统凭据库（keyring）：Windows=凭据管理器 / macOS=Keychain。
- profiles.json 只存非敏感字段（host/user/分区等）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from typing import Optional

from . import config

try:
    import keyring
    _KEYRING_OK = True
except Exception:  # keyring 后端缺失也不崩，退化为「本会话内存密码」
    keyring = None
    _KEYRING_OK = False


@dataclass
class Profile:
    name: str
    host: str = ""
    port: int = 22
    username: str = ""
    # 认证方式: "password" 或 "key"
    auth_method: str = "password"
    key_path: str = ""              # 私钥文件路径（auth_method=key 时）
    slurm_account: str = ""
    partition: str = ""
    qos: str = ""
    default_remote_dir: str = ""
    python_path: str = ""           # 远端 conda python 绝对路径（提交脚本用）
    vpn_note: str = ""

    def keyring_user(self) -> str:
        return f"{self.username}@{self.host}:{self.port}"


class ProfileStore:
    """profiles.json 的增删改查 + 密码 keyring 读写。"""

    def __init__(self) -> None:
        self._path = config.profiles_path()
        self._profiles: dict[str, Profile] = {}
        self._mem_pw: dict[str, str] = {}  # keyring 不可用时的退化缓存
        self.load()

    # ---- 持久化 ----
    def load(self) -> None:
        self._profiles.clear()
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        for item in raw.get("profiles", []):
            try:
                p = Profile(**item)
                self._profiles[p.name] = p
            except TypeError:
                # 兼容旧/多余字段
                allowed = Profile.__dataclass_fields__.keys()
                p = Profile(**{k: v for k, v in item.items() if k in allowed})
                self._profiles[p.name] = p

    def save(self) -> None:
        data = {"profiles": [asdict(p) for p in self._profiles.values()]}
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ---- CRUD ----
    def list(self) -> list[Profile]:
        return list(self._profiles.values())

    def get(self, name: str) -> Optional[Profile]:
        return self._profiles.get(name)

    def upsert(self, profile: Profile, password: Optional[str] = None) -> None:
        self._profiles[profile.name] = profile
        self.save()
        if password is not None:
            self.set_password(profile, password)

    def delete(self, name: str) -> None:
        p = self._profiles.pop(name, None)
        if p is not None:
            self.save()
            self._delete_password(p)

    # ---- 密码（keyring）----
    def set_password(self, profile: Profile, password: str) -> None:
        key = profile.keyring_user()
        if _KEYRING_OK:
            try:
                keyring.set_password(config.KEYRING_SERVICE, key, password)
                return
            except Exception:
                pass
        self._mem_pw[key] = password

    def get_password(self, profile: Profile) -> Optional[str]:
        key = profile.keyring_user()
        if _KEYRING_OK:
            try:
                pw = keyring.get_password(config.KEYRING_SERVICE, key)
                if pw is not None:
                    return pw
            except Exception:
                pass
        return self._mem_pw.get(key)

    def _delete_password(self, profile: Profile) -> None:
        key = profile.keyring_user()
        if _KEYRING_OK:
            try:
                keyring.delete_password(config.KEYRING_SERVICE, key)
            except Exception:
                pass
        self._mem_pw.pop(key, None)

    @property
    def keyring_available(self) -> bool:
        return _KEYRING_OK
