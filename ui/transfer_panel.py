"""SFTP 双栏文件传输面板。

左=本地，右=远端；双击进目录，↑ 返回上级。
上传/下载带进度条；远端可新建目录、删除。
"""
from __future__ import annotations

import os
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QMessageBox, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from core.worker import run_async, run_with_progress
from .app_context import AppContext


def _fmt_size(n: int) -> str:
    f = float(n)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if f < 1024 or u == "TB":
            return f"{f:.0f} {u}" if u == "B" else f"{f:.1f} {u}"
        f /= 1024
    return f"{n} B"


class _Browser(QWidget):
    """单栏文件浏览（本地或远端共用，差异在加载函数）。"""

    def __init__(self, title: str) -> None:
        super().__init__()
        v = QVBoxLayout(self)
        self.vbox = v
        v.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.btn_up = QPushButton("↑ 上级")
        self.path_edit = QLineEdit()
        self.path_edit.returnPressed.connect(self._go)
        self.btn_go = QPushButton("转到")
        self.btn_go.clicked.connect(self._go)
        top.addWidget(QLabel(title))
        top.addWidget(self.btn_up)
        top.addWidget(self.path_edit, 1)
        top.addWidget(self.btn_go)
        v.addLayout(top)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["名称", "大小", "修改时间"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(self._on_dbl)
        v.addWidget(self.table)
        self.cwd = ""
        self._entries: list[tuple[str, bool, int, float]] = []  # name,is_dir,size,mtime
        # 由子类/外部赋值
        self.on_navigate = lambda path: None

    def _go(self) -> None:
        self.on_navigate(self.path_edit.text().strip())

    def _on_dbl(self, row: int, _col: int) -> None:
        if 0 <= row < len(self._entries):
            name, is_dir, *_ = self._entries[row]
            if is_dir:
                self.on_navigate(self._join(self.cwd, name))

    def _join(self, base: str, name: str) -> str:
        raise NotImplementedError

    def populate(self, cwd: str, entries: list[tuple[str, bool, int, float]]) -> None:
        self.cwd = cwd
        self.path_edit.setText(cwd)
        self._entries = sorted(entries, key=lambda e: (not e[1], e[0].lower()))
        self.table.setRowCount(len(self._entries))
        for r, (name, is_dir, size, mtime) in enumerate(self._entries):
            disp = ("📁 " if is_dir else "📄 ") + name
            self.table.setItem(r, 0, QTableWidgetItem(disp))
            self.table.setItem(r, 1, QTableWidgetItem("" if is_dir else _fmt_size(size)))
            ts = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M") if mtime else ""
            self.table.setItem(r, 2, QTableWidgetItem(ts))

    def selected_names(self) -> list[tuple[str, bool]]:
        rows = {i.row() for i in self.table.selectedIndexes()}
        out = []
        for r in sorted(rows):
            if 0 <= r < len(self._entries):
                name, is_dir, *_ = self._entries[r]
                out.append((name, is_dir))
        return out


class _LocalBrowser(_Browser):
    def __init__(self, title: str) -> None:
        super().__init__(title)
        # Windows 盘符切换栏（C/D/E…），插到地址栏下方
        drives = self._list_drives()
        if drives:
            row = QHBoxLayout()
            row.addWidget(QLabel("盘符"))
            self.drive_cmb = QComboBox()
            self.drive_cmb.addItems(drives)
            self.drive_cmb.activated.connect(self._on_drive)
            row.addWidget(self.drive_cmb)
            row.addStretch(1)
            self.vbox.insertLayout(1, row)
        else:
            self.drive_cmb = None

    @staticmethod
    def _list_drives() -> list[str]:
        if os.name != "nt":
            return []
        out = []
        for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            p = f"{c}:\\"
            if os.path.exists(p):
                out.append(p)
        return out

    def _on_drive(self, _i: int) -> None:
        if self.drive_cmb:
            self.on_navigate(self.drive_cmb.currentText())

    def _join(self, base: str, name: str) -> str:
        return os.path.normpath(os.path.join(base, name))


class _RemoteBrowser(_Browser):
    def _join(self, base: str, name: str) -> str:
        return (base.rstrip("/") + "/" + name) if base != "/" else "/" + name


class TransferPanel(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx

        root = QVBoxLayout(self)
        panes = QHBoxLayout()

        self.local = _LocalBrowser("本地")
        self.local.on_navigate = self._nav_local
        self.local._join = lambda b, n: os.path.normpath(os.path.join(b, n))
        self.local.btn_up.clicked.connect(
            lambda: self._nav_local(os.path.dirname(self.local.cwd.rstrip("/\\")) or self.local.cwd))

        mid = QVBoxLayout()
        mid.addStretch(1)
        self.btn_upload = QPushButton("上传 →")
        self.btn_upload.setObjectName("primary")
        self.btn_download = QPushButton("← 下载")
        self.btn_upload.clicked.connect(self._upload)
        self.btn_download.clicked.connect(self._download)
        mid.addWidget(self.btn_upload)
        mid.addWidget(self.btn_download)
        mid.addStretch(1)
        mid_w = QWidget()
        mid_w.setLayout(mid)
        mid_w.setFixedWidth(110)

        self.remote = _RemoteBrowser("远端 (HPC)")
        self.remote.on_navigate = self._nav_remote
        self.remote.btn_up.clicked.connect(self._remote_up)

        panes.addWidget(self.local, 1)
        panes.addWidget(mid_w)
        panes.addWidget(self.remote, 1)
        root.addLayout(panes, 1)

        rbtns = QHBoxLayout()
        self.btn_mkdir = QPushButton("远端新建目录")
        self.btn_rmt_refresh = QPushButton("远端刷新")
        self.btn_rm = QPushButton("远端删除")
        self.btn_rm.setObjectName("danger")
        self.btn_mkdir.clicked.connect(self._mkdir)
        self.btn_rmt_refresh.clicked.connect(lambda: self._nav_remote(self.remote.cwd))
        self.btn_rm.clicked.connect(self._rm_remote)
        rbtns.addStretch(1)
        rbtns.addWidget(self.btn_mkdir)
        rbtns.addWidget(self.btn_rmt_refresh)
        rbtns.addWidget(self.btn_rm)
        root.addLayout(rbtns)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.lbl_prog = QLabel("就绪")
        self.lbl_prog.setObjectName("hint")
        root.addWidget(self.lbl_prog)
        root.addWidget(self.progress)

        self.ctx.connected.connect(self._on_connected)
        self.ctx.disconnected.connect(self._on_disconnected)
        self._set_remote_enabled(False)
        # 本地起点：用户主目录
        self._nav_local(os.path.expanduser("~"))

    def _set_remote_enabled(self, on: bool) -> None:
        for w in (self.btn_upload, self.btn_download, self.btn_mkdir,
                  self.btn_rmt_refresh, self.btn_rm, self.remote):
            w.setEnabled(on)

    def _on_connected(self, profile) -> None:
        self._set_remote_enabled(True)
        start = profile.default_remote_dir or "."
        self._nav_remote(start)

    def _on_disconnected(self) -> None:
        self._set_remote_enabled(False)
        self.remote.table.setRowCount(0)

    # ---- 本地导航 ----
    def _nav_local(self, path: str) -> None:
        if not path:
            return
        # "D:" → "D:\"，容错盘符无斜杠 / 多余引号空格
        path = path.strip().strip('"')
        if len(path) == 2 and path[1] == ":":
            path += "\\"
        if not os.path.isdir(path):
            QMessageBox.warning(self, "本地", f"目录不存在：{path}")
            return
        try:
            entries = []
            for name in os.listdir(path):
                fp = os.path.join(path, name)
                try:
                    st = os.stat(fp)
                    entries.append((name, os.path.isdir(fp), st.st_size, st.st_mtime))
                except OSError:
                    continue
            abspath = os.path.abspath(path)
            self.local.populate(abspath, entries)
            # 同步盘符下拉到当前盘
            cmb = getattr(self.local, "drive_cmb", None)
            if cmb is not None and len(abspath) >= 2 and abspath[1] == ":":
                cur = abspath[0].upper() + ":\\"
                idx = cmb.findText(cur)
                if idx >= 0:
                    cmb.blockSignals(True)
                    cmb.setCurrentIndex(idx)
                    cmb.blockSignals(False)
        except OSError as e:
            QMessageBox.warning(self, "本地", str(e))

    # ---- 远端导航 ----
    def _nav_remote(self, path: str) -> None:
        if not self.ctx.is_connected:
            QMessageBox.information(
                self, "未连接",
                "远端未连接。先到「连接」页点「保存并连接」，再用远端浏览。")
            return
        path = path or "."

        def do():
            ssh = self.ctx.ssh
            real = ssh.normalize(path)
            items = ssh.listdir(real)
            return real, [(e.name, e.is_dir, e.size, e.mtime) for e in items]

        run_async(self, do,
                  on_ok=lambda res: self.remote.populate(res[0], res[1]),
                  on_err=lambda m: QMessageBox.warning(self, "远端", m))

    def _remote_up(self) -> None:
        cwd = self.remote.cwd
        parent = cwd.rstrip("/").rsplit("/", 1)[0] or "/"
        self._nav_remote(parent)

    # ---- 上传 ----
    def _upload(self) -> None:
        sel = self.local.selected_names()
        files = [(n, d) for n, d in sel if not d]
        dirs = [n for n, d in sel if d]
        if dirs:
            QMessageBox.information(
                self, "目录上传",
                "暂只支持文件上传。大目录建议先本地打包 zip 再上传，"
                "远端用「任务监控/终端」解压（或后续版本加自动 zip）。")
        if not files:
            return
        remote_dir = self.remote.cwd
        queue = [os.path.join(self.local.cwd, n) for n, _ in files]
        self._run_transfer(queue, remote_dir, upload=True)

    def _download(self) -> None:
        sel = self.remote.selected_names()
        files = [n for n, d in sel if not d]
        if any(d for _, d in sel):
            QMessageBox.information(self, "目录下载", "暂只支持文件下载。")
        if not files:
            return
        local_dir = self.local.cwd
        queue = [self.remote._join(self.remote.cwd, n) for n in files]
        self._run_transfer(queue, local_dir, upload=False)

    def _run_transfer(self, queue: list[str], dest: str, upload: bool) -> None:
        import time
        total = len(queue)
        self._cur_name = ""
        self._cur_idx = 0
        self._cur_total = total

        def step(idx: int):
            if idx >= total:
                self.lbl_prog.setText(f"✓ 完成 {total} 个文件")
                self.progress.setValue(100)
                # 上传完刷新远端、下载完刷新本地
                (self._nav_remote(self.remote.cwd) if upload
                 else self._nav_local(self.local.cwd))
                return
            src = queue[idx]
            name = os.path.basename(src) if upload else src.rstrip("/").rsplit("/", 1)[-1]
            self._cur_name = name
            self._cur_idx = idx
            self._tx_t0 = time.time()
            self.lbl_prog.setText(f"[{idx+1}/{total}] {name} —— 准备中…")
            self.progress.setValue(0)

            if upload:
                rpath = self.remote._join(dest, name)
                # 断点续传：远端有半截就接着传
                fn = lambda prog, s=src, r=rpath: self.ctx.ssh.put_resume(s, r, progress=prog)
                done_cb = lambda _i=idx: (self._nav_remote(self.remote.cwd), step(_i + 1))
            else:
                lpath = os.path.join(dest, name)
                fn = lambda prog, s=src, l=lpath: self.ctx.ssh.get_resume(s, l, progress=prog)
                done_cb = lambda _i=idx: step(_i + 1)

            run_with_progress(
                self, fn,
                on_ok=lambda _r, cb=done_cb: cb(),
                on_err=lambda m: (QMessageBox.warning(
                    self, "传输失败",
                    f"{m}\n\n已传部分保留，重新点上传/下载会自动断点续传。"),
                    self.lbl_prog.setText("✗ 传输中断（可断点续传）")),
                on_progress=self._on_prog)

        step(0)

    def _on_prog(self, done: int, total: int) -> None:
        import time
        if total <= 0:
            return
        pct = int(done * 100 / total)
        self.progress.setValue(pct)
        elapsed = max(time.time() - getattr(self, "_tx_t0", time.time()), 1e-6)
        speed = done / elapsed  # B/s
        eta = (total - done) / speed if speed > 0 else 0
        self.lbl_prog.setText(
            f"[{self._cur_idx+1}/{self._cur_total}] {self._cur_name} —— "
            f"{_fmt_size(done)}/{_fmt_size(total)} · "
            f"{_fmt_size(int(speed))}/s · 剩 {self._fmt_eta(eta)}")

    @staticmethod
    def _fmt_eta(sec: float) -> str:
        sec = int(sec)
        if sec < 60:
            return f"{sec}s"
        if sec < 3600:
            return f"{sec//60}m{sec%60}s"
        return f"{sec//3600}h{(sec%3600)//60}m"

    # ---- 远端目录操作 ----
    def _mkdir(self) -> None:
        name, ok = QInputDialog.getText(self, "新建目录", "目录名：")
        if not (ok and name.strip()):
            return
        path = self.remote._join(self.remote.cwd, name.strip())
        run_async(self, lambda: self.ctx.ssh.mkdirs(path),
                  on_ok=lambda _: self._nav_remote(self.remote.cwd),
                  on_err=lambda m: QMessageBox.warning(self, "新建目录", m))

    def _rm_remote(self) -> None:
        sel = self.remote.selected_names()
        if not sel:
            return
        names = ", ".join(n for n, _ in sel)
        if QMessageBox.question(
                self, "删除", f"删除远端：{names}？\n（目录会递归删除，不可恢复）")\
                != QMessageBox.StandardButton.Yes:
            return
        paths = [(self.remote._join(self.remote.cwd, n), d) for n, d in sel]

        def do():
            import shlex
            for p, is_dir in paths:
                flag = "-rf" if is_dir else "-f"
                self.ctx.ssh.exec(f"rm {flag} {shlex.quote(p)}")
            return True

        run_async(self, do,
                  on_ok=lambda _: self._nav_remote(self.remote.cwd),
                  on_err=lambda m: QMessageBox.warning(self, "删除", m))
