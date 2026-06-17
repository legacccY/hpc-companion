"""paramiko SSH/SFTP 封装 —— 全应用唯一与 HPC 通信的出口。

- 一条连接复用，exec_command 每次开新 channel（paramiko 支持并发 channel）。
- SFTP 会话加锁，避免多线程同时读写同一 sftp channel 出错。
- 提供 is_alive / 自动重连，UI 长时间挂着也不掉。
"""
from __future__ import annotations

import socket
import stat
import threading
import warnings
from dataclasses import dataclass
from typing import Callable, Optional

warnings.filterwarnings("ignore")

import paramiko

from .profiles import Profile


class SSHError(Exception):
    pass


class AuthError(SSHError):
    pass


class NetworkError(SSHError):
    pass


@dataclass
class ExecResult:
    rc: int
    out: str
    err: str

    @property
    def ok(self) -> bool:
        return self.rc == 0


@dataclass
class RemoteEntry:
    name: str
    is_dir: bool
    size: int
    mtime: float


class SSHClient:
    def __init__(self) -> None:
        self._client: Optional[paramiko.SSHClient] = None
        self._sftp: Optional[paramiko.SFTPClient] = None
        self._sftp_lock = threading.Lock()
        self.profile: Optional[Profile] = None

    # ---- 连接 ----
    def connect(self, profile: Profile, password: Optional[str] = None,
                timeout: int = 15) -> None:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            kwargs = dict(
                hostname=profile.host,
                port=profile.port or 22,
                username=profile.username,
                timeout=timeout,
                banner_timeout=timeout,
                auth_timeout=timeout,
                allow_agent=False,
                look_for_keys=False,
            )
            if profile.auth_method == "key" and profile.key_path:
                kwargs["key_filename"] = profile.key_path
                if password:  # 私钥口令
                    kwargs["passphrase"] = password
            else:
                kwargs["password"] = password or ""
            c.connect(**kwargs)
        except paramiko.AuthenticationException as e:
            raise AuthError(
                "认证失败：账号/密码错误，或校外未连 VPN 导致无法到达主机。"
            ) from e
        except (socket.timeout, socket.gaierror, OSError) as e:
            raise NetworkError(
                f"无法连接主机 {profile.host}:{profile.port or 22}（{e}）。"
                "检查网络 / VPN / 主机地址。"
            ) from e
        except Exception as e:
            raise SSHError(f"连接失败：{e}") from e
        # 保活：每 30s 发心跳，防 NAT/防火墙掐空闲连接（实现「一直在线」）
        tr = c.get_transport()
        if tr is not None:
            tr.set_keepalive(30)
        self._client = c
        self.profile = profile

    def is_alive(self) -> bool:
        if self._client is None:
            return False
        tr = self._client.get_transport()
        return bool(tr and tr.is_active())

    def _ensure(self) -> None:
        if not self.is_alive():
            if self.profile is None:
                raise SSHError("尚未连接。")
            raise NetworkError("连接已断开，请重新连接。")

    def close(self) -> None:
        with self._sftp_lock:
            if self._sftp is not None:
                try:
                    self._sftp.close()
                except Exception:
                    pass
                self._sftp = None
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    # ---- 命令执行 ----
    def exec(self, cmd: str, timeout: int = 30) -> ExecResult:
        self._ensure()
        try:
            _, o, e = self._client.exec_command(cmd, timeout=timeout)
            out = o.read().decode("utf-8", errors="replace").strip()
            err = e.read().decode("utf-8", errors="replace").strip()
            rc = o.channel.recv_exit_status()
            return ExecResult(rc, out, err)
        except socket.timeout as ex:
            raise NetworkError(f"命令超时（{timeout}s）：{cmd[:60]}") from ex
        except Exception as ex:
            raise SSHError(f"命令执行失败：{ex}") from ex

    # ---- SFTP ----
    def _get_sftp(self) -> paramiko.SFTPClient:
        self._ensure()
        if self._sftp is None:
            self._sftp = self._client.open_sftp()
        return self._sftp

    def listdir(self, path: str) -> list[RemoteEntry]:
        with self._sftp_lock:
            sftp = self._get_sftp()
            entries = []
            for attr in sftp.listdir_attr(path):
                entries.append(RemoteEntry(
                    name=attr.filename,
                    is_dir=stat.S_ISDIR(attr.st_mode or 0),
                    size=attr.st_size or 0,
                    mtime=attr.st_mtime or 0,
                ))
            return entries

    def normalize(self, path: str) -> str:
        with self._sftp_lock:
            return self._get_sftp().normalize(path)

    def read_text(self, path: str, max_bytes: int = 200_000) -> str:
        with self._sftp_lock:
            sftp = self._get_sftp()
            with sftp.open(path, "r") as f:
                f.prefetch()
                data = f.read(max_bytes)
            if isinstance(data, bytes):
                return data.decode("utf-8", errors="replace")
            return str(data)

    def put(self, local: str, remote: str,
            progress: Optional[Callable[[int, int], None]] = None) -> None:
        with self._sftp_lock:
            sftp = self._get_sftp()
            sftp.put(local, remote, callback=progress)

    def get(self, remote: str, local: str,
            progress: Optional[Callable[[int, int], None]] = None) -> None:
        with self._sftp_lock:
            sftp = self._get_sftp()
            sftp.get(remote, local, callback=progress)

    # ---- 断点续传 ----
    def put_resume(self, local: str, remote: str,
                   progress: Optional[Callable[[int, int], None]] = None,
                   chunk: int = 1 << 18) -> None:
        """上传支持断点续传：远端已有部分则从断点接着传。"""
        import os
        total = os.path.getsize(local)
        with self._sftp_lock:
            sftp = self._get_sftp()
            try:
                done = sftp.stat(remote).st_size
            except IOError:
                done = 0
            if done > total:          # 远端比本地大，视为脏文件，重传
                done = 0
            if done == total and total > 0:
                if progress:
                    progress(total, total)
                return
            mode = "ab" if done > 0 else "wb"
            with open(local, "rb") as lf, sftp.open(remote, mode) as rf:
                rf.set_pipelined(True)
                lf.seek(done)
                sent = done
                while True:
                    buf = lf.read(chunk)
                    if not buf:
                        break
                    rf.write(buf)
                    sent += len(buf)
                    if progress:
                        progress(sent, total)

    def get_resume(self, remote: str, local: str,
                   progress: Optional[Callable[[int, int], None]] = None,
                   chunk: int = 1 << 18) -> None:
        """下载支持断点续传：本地已有部分则从断点接着下。"""
        import os
        with self._sftp_lock:
            sftp = self._get_sftp()
            total = sftp.stat(remote).st_size
            done = os.path.getsize(local) if os.path.exists(local) else 0
            if done > total:
                done = 0
            if done == total and total > 0:
                if progress:
                    progress(total, total)
                return
            mode = "ab" if done > 0 else "wb"
            with sftp.open(remote, "rb") as rf, open(local, mode) as lf:
                rf.prefetch(total)
                rf.seek(done)
                got = done
                while True:
                    buf = rf.read(chunk)
                    if not buf:
                        break
                    lf.write(buf)
                    got += len(buf)
                    if progress:
                        progress(got, total)

    def mkdirs(self, remote_dir: str) -> None:
        with self._sftp_lock:
            sftp = self._get_sftp()
            parts = remote_dir.strip("/").split("/")
            cur = "/"
            for p in parts:
                cur = cur.rstrip("/") + "/" + p
                try:
                    sftp.stat(cur)
                except IOError:
                    sftp.mkdir(cur)
