"""任务监控面板。

上：squeue 任务表（自动刷新、状态着色、取消）。
下：选中 job 的详情 / 日志 tail / GPU 利用率曲线。
日志路径自动从 scontrol 的 StdOut/StdErr 取，无需手填。
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTabWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)  # noqa

import pyqtgraph as pg

from core import slurm
from core.worker import run_async
from .app_context import AppContext
from . import theme

pg.setConfigOption("background", theme.palette()["BG_ALT"])
pg.setConfigOption("foreground", theme.palette()["TEXT"])
pg.setConfigOptions(antialias=True)  # 曲线抗锯齿，平滑不生硬

FAIL_STATES = {"FAILED", "TIMEOUT", "OUT_OF_MEMORY", "CANCELLED", "NODE_FAIL", "BOOT_FAIL"}


class JobsPanel(QWidget):
    GPU_WIN = 60      # GPU 曲线可见点数（固定时间窗，滚动）
    BUF_MAX = 600     # 曲线缓冲硬上限，防 1s 刷新内存堆积

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self._jobs: list[slurm.Job] = []
        self._n_active: int = 0
        self._sel_job: str | None = None
        self._gpu_t: list[float] = []
        self._gpu_sm: list[float] = []
        self._gpu_mem: list[float] = []
        self._gpu_n = 0   # 单调采样计数，作 X（缓冲裁剪后仍递增→滚动正确）
        self._detail_busy = False   # 详情/日志在途标记，防快档刷新堆积
        self._gpu_busy = False      # GPU dmon 在途标记（dmon 慢，最易堆）
        self._logpath_cache: dict = {}   # (jid,ext) -> 已定位日志路径，find 只跑一次
        self._tick = 0

        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.addLayout(self._build_controls())

        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self._build_table())
        split.addWidget(self._build_detail())
        split.setSizes([260, 420])
        root.addWidget(split, 1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)

        self.ctx.connected.connect(self._on_connected)
        self.ctx.disconnected.connect(self._on_disconnected)
        self._set_enabled(False)
        self.apply_theme()

    # ---- 顶部控制 ----
    def _build_controls(self) -> QHBoxLayout:
        lay = QHBoxLayout()
        self.btn_refresh = QPushButton("立即刷新")
        self.btn_refresh.clicked.connect(self.refresh)
        self.chk_auto = QCheckBox("自动刷新")
        self.chk_auto.setChecked(True)
        self.chk_auto.toggled.connect(self._toggle_auto)
        self.cmb_interval = QComboBox()
        for s in ("1 秒", "5 秒", "10 秒", "15 秒", "30 秒", "60 秒", "5 分钟"):
            self.cmb_interval.addItem(s)
        self.cmb_interval.setCurrentText("10 秒")
        self.cmb_interval.currentTextChanged.connect(self._toggle_auto)
        self.chk_history = QCheckBox("显示已结束")
        self.chk_history.setChecked(True)
        self.chk_history.toggled.connect(self.refresh)
        self.cmb_range = QComboBox()
        for s in ("今日", "近 3 天", "近 7 天", "近 30 天"):
            self.cmb_range.addItem(s)
        self.cmb_range.currentTextChanged.connect(self.refresh)
        self.lbl_tick = QLabel("")
        self.lbl_tick.setObjectName("hint")
        lay.addWidget(self.btn_refresh)
        lay.addWidget(self.chk_auto)
        lay.addWidget(QLabel("间隔"))
        lay.addWidget(self.cmb_interval)
        lay.addWidget(self.chk_history)
        lay.addWidget(self.cmb_range)
        lay.addWidget(self.lbl_tick)
        lay.addStretch(1)
        self.btn_cancel = QPushButton("取消选中任务")
        self.btn_cancel.setObjectName("danger")
        self.btn_cancel.clicked.connect(self._cancel_job)
        lay.addWidget(self.btn_cancel)
        return lay

    def _make_util_plot(self, title: str, color_key: str):
        """0-100% 锁死、禁缩放、半透明填充的滚动利用率图（任务管理器式）。"""
        plot = pg.PlotWidget()
        plot.setTitle(title)
        plot.setLabel("left", "%")
        plot.setLabel("bottom", "采样次")
        plot.showGrid(x=True, y=True, alpha=0.2)
        vb = plot.getViewBox()
        vb.setMouseEnabled(x=False, y=False)
        vb.setYRange(0, 100, padding=0)
        vb.setLimits(yMin=0, yMax=100)
        plot.setMenuEnabled(False)
        col = QColor(theme.palette()[color_key])
        fill = QColor(col); fill.setAlpha(60)
        curve = plot.plot(pen=pg.mkPen(col, width=2), fillLevel=0, brush=pg.mkBrush(fill))
        plot.setXRange(0, self.GPU_WIN, padding=0)
        return plot, curve

    def _build_table(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Job ID", "名称", "状态", "运行时长", "节点", "原因/节点列表"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        v.addWidget(self.table)
        return w

    def _build_detail(self) -> QWidget:
        self.tabs = QTabWidget()

        # 日志
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        log_w = QWidget()
        lv = QVBoxLayout(log_w)
        bar = QHBoxLayout()
        self.cmb_logsrc = QComboBox()
        self.cmb_logsrc.addItems(["标准输出 (.out)", "错误输出 (.err)"])
        self.cmb_logsrc.currentTextChanged.connect(self._refresh_detail)
        bar.addWidget(QLabel("日志源"))
        bar.addWidget(self.cmb_logsrc)
        bar.addStretch(1)
        self.lbl_logpath = QLabel("")
        self.lbl_logpath.setObjectName("hint")
        bar.addWidget(self.lbl_logpath)
        lv.addLayout(bar)
        lv.addWidget(self.log_view)
        self.tabs.addTab(log_w, "日志")

        # GPU / 显存 曲线（下方坐标拆左右两栏：左 GPU 利用率 / 右 显存利用率）
        gpu_w = QWidget()
        gv = QVBoxLayout(gpu_w)
        self.lbl_gpu = QLabel("GPU：选中运行中的任务后显示")
        self.lbl_gpu.setObjectName("hint")
        gv.addWidget(self.lbl_gpu)
        plots = QHBoxLayout()
        self.gpu_plot, self.gpu_curve = self._make_util_plot("GPU 利用率 (SM %)", "ACCENT")
        self.mem_plot, self.mem_curve = self._make_util_plot("显存利用率 (Mem %)", "WARN")
        plots.addWidget(self.gpu_plot)
        plots.addWidget(self.mem_plot)
        gv.addLayout(plots)
        self.gpu_tab = gpu_w            # 句柄：仅此页可见时才采 GPU（省 srun dmon）
        self.tabs.addTab(gpu_w, "GPU / 显存")

        # 详情
        self.detail_view = QPlainTextEdit()
        self.detail_view.setReadOnly(True)
        self.tabs.addTab(self.detail_view, "scontrol 详情")
        self.tabs.currentChanged.connect(self._on_subtab_changed)

        # 容器：顶部错误横幅（失败任务变红显错）+ 标签页
        cont = QWidget()
        cl = QVBoxLayout(cont)
        cl.setContentsMargins(0, 0, 0, 0)
        self.err_banner = QLabel("")
        self.err_banner.setWordWrap(True)
        self.err_banner.setVisible(False)
        self.err_banner.setStyleSheet(
            f"background:{theme.palette()['DANGER']}; color:#fff; "
            f"padding:8px 12px; border-radius:6px; font-weight:600;")
        cl.addWidget(self.err_banner)
        cl.addWidget(self.tabs, 1)
        return cont

    # ---- 连接状态 ----
    def _set_enabled(self, on: bool) -> None:
        for w in (self.btn_refresh, self.chk_auto, self.cmb_interval,
                  self.btn_cancel, self.table):
            w.setEnabled(on)

    def _on_connected(self, _profile) -> None:
        self._set_enabled(True)
        self.refresh()
        if self.chk_auto.isChecked():
            self._toggle_auto()

    def _on_disconnected(self) -> None:
        self.timer.stop()
        self._set_enabled(False)
        self.table.setRowCount(0)

    def _interval_ms(self) -> int:
        return {"1 秒": 1000, "5 秒": 5000, "10 秒": 10000, "15 秒": 15000,
                "30 秒": 30000, "60 秒": 60000,
                "5 分钟": 300000}[self.cmb_interval.currentText()]

    def _toggle_auto(self, *_) -> None:
        if self.chk_auto.isChecked() and self.ctx.is_connected:
            self.timer.start(self._interval_ms())
        else:
            self.timer.stop()

    # ---- 刷新 squeue ----
    def refresh(self) -> None:
        if not self.ctx.is_connected or self.ctx.profile is None:
            return
        self._tick += 1
        user = self.ctx.profile.username
        want_hist = self.chk_history.isChecked()
        days = {"今日": 0, "近 3 天": 3, "近 7 天": 7, "近 30 天": 30}[self.cmb_range.currentText()]

        def do():
            sq = slurm.parse_squeue(self.ctx.ssh.exec(slurm.queue_cmd(user), timeout=20).out)
            hist = []
            if want_hist:
                hist = slurm.parse_sacct(
                    self.ctx.ssh.exec(slurm.sacct_cmd(user, days), timeout=30).out)
            return sq, hist

        run_async(self, do, on_ok=self._fill_table, on_err=self._err)
        # 选中的任务，刷新表的同时刷它的日志/GPU/心跳，实现"实时看"
        if self._sel_job:
            self._refresh_detail()

    def _fill_table(self, data) -> None:
        sq, hist = data
        # 融合：sacct 历史打底，squeue 活跃任务覆盖（活跃状态更准）
        active_ids = {j.job_id for j in sq}
        ended = [j for j in hist if j.job_id not in active_ids]
        ended.sort(key=lambda j: j.job_id, reverse=True)
        self._jobs = sq + ended
        self._n_active = len(sq)
        prev = self._sel_job
        sc = theme.state_colors()
        self.table.setRowCount(len(self._jobs))
        for r, j in enumerate(self._jobs):
            vals = [j.job_id, j.name, j.state, j.time, j.nodes, j.reason]
            for c, val in enumerate(vals):
                item = QTableWidgetItem(val)
                if c == 2:
                    color = sc.get(j.state)
                    if color:
                        item.setForeground(QColor(color))
                self.table.setItem(r, c, item)
        n_ended = len(self._jobs) - self._n_active
        self.lbl_tick.setText(
            f"刷新#{self._tick} · 活跃 {self._n_active} · 已结束 {n_ended}"
            + ("（无任务）" if not self._jobs else ""))
        # 维持选中
        if prev:
            for r, j in enumerate(self._jobs):
                if j.job_id == prev:
                    self.table.selectRow(r)
                    break

    # ---- 选中行 ----
    def _on_row_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        r = rows[0].row()
        if 0 <= r < len(self._jobs):
            new = self._jobs[r].job_id
            if new != self._sel_job:
                self._sel_job = new
                self._gpu_t.clear(); self._gpu_sm.clear()
                self._gpu_mem.clear(); self._gpu_n = 0
            self._refresh_detail()

    def _cur_state(self) -> str:
        for j in self._jobs:
            if j.job_id == self._sel_job:
                return j.state
        return ""

    def _refresh_detail(self, *_) -> None:
        if not self._sel_job or not self.ctx.is_connected:
            return
        if self._detail_busy:        # 上一轮详情还没回来，跳过本次（防快档堆积）
            return
        jid = self._sel_job
        cur_state = self._cur_state()
        # GPU 采样只在「GPU / 显存」子页可见时做，省每 tick 一次慢 srun dmon
        want_gpu = cur_state == "RUNNING" and self.tabs.currentWidget() is self.gpu_tab
        want_err = self.cmb_logsrc.currentIndex() == 1
        ext = "err" if want_err else "out"

        def do():
            ssh = self.ctx.ssh
            d = slurm.parse_scontrol(ssh.exec(slurm.detail_cmd(jid)).out)
            workdir = d.get("WorkDir", "")
            if workdir in ("(null)", ""):
                workdir = ""
            if not workdir:
                wd = ssh.exec(f"sacct -j {jid} -X -n --format=WorkDir%500 2>/dev/null").out.strip()
                workdir = wd.splitlines()[0].strip() if wd else ""

            def locate(want_ext: str) -> str:
                """先用 scontrol 的 StdOut/StdErr；清理后用 find 按 job id 搜（结果缓存）。"""
                lp = d.get("StdErr" if want_ext == "err" else "StdOut", "")
                if lp in ("(null)", ""):
                    lp = ""
                if lp:
                    return lp
                ck = (jid, want_ext)
                if ck in self._logpath_cache:      # find 每个 job 只跑一次
                    return self._logpath_cache[ck]
                roots = []
                if workdir:
                    roots.append(workdir.rstrip("/"))
                prof = self.ctx.profile
                if prof and prof.default_remote_dir:
                    roots.append(prof.default_remote_dir.rstrip("/"))
                result = ""
                seen = set()
                for root in roots:
                    if not root or root in seen:
                        continue
                    seen.add(root)
                    found = ssh.exec(
                        f"find '{root}' -maxdepth 4 -name '*{jid}*' -type f "
                        f"2>/dev/null | head -20").out.strip().splitlines()
                    if found:
                        pref = [f for f in found if f.endswith(f".{want_ext}")]
                        result = (pref or found)[0].strip()
                        break
                self._logpath_cache[ck] = result
                return result

            log_path = locate(ext)
            log_tail = ssh.exec(f"tail -n 300 '{log_path}' 2>/dev/null").out if log_path else ""

            # 失败任务 → 抓 .err 末尾 + 退出码，做红色错误摘要
            err_summary = ""
            if cur_state in FAIL_STATES:
                err_path = log_path if ext == "err" else locate("err")
                err_tail = ssh.exec(f"tail -n 15 '{err_path}' 2>/dev/null").out if err_path else ""
                exitcode = d.get("ExitCode", "")
                if not exitcode:
                    ec = ssh.exec(f"sacct -j {jid} -X -n --format=ExitCode 2>/dev/null").out.strip().splitlines()
                    exitcode = ec[0].strip() if ec else ""
                err_summary = self._build_err_summary(
                    cur_state, exitcode, d.get("Reason", ""), err_tail)

            detail_txt = self._fmt_detail(d) if d else ""
            return dict(detail=detail_txt, log=log_tail, log_path=log_path,
                        state=cur_state, err=err_summary)

        self._detail_busy = True

        def _done(d):
            self._detail_busy = False
            self._apply_detail(d)

        def _fail(m):
            self._detail_busy = False
            self._err(m)

        run_async(self, do, on_ok=_done, on_err=_fail)
        # GPU 采样慢（srun dmon ~数秒），单独异步，不拖累日志/详情秒出
        if want_gpu:
            self._refresh_gpu(jid)

    def _on_subtab_changed(self, *_) -> None:
        # 切到 GPU 子页且任务在跑 → 立刻采一次，不等下个 tick
        if (self._sel_job and self._cur_state() == "RUNNING"
                and self.tabs.currentWidget() is self.gpu_tab):
            self._refresh_gpu(self._sel_job)

    def _refresh_gpu(self, jid: str) -> None:
        if self._gpu_busy:           # dmon 慢，上一轮没回别再发（防堆积）
            return
        self._gpu_busy = True

        def do():
            graw = self.ctx.ssh.exec(slurm.gpu_dmon_cmd(jid, 3), timeout=20).out
            return slurm.parse_gpu_dmon(graw)

        def _done(g):
            self._gpu_busy = False
            self._apply_gpu(g, jid)

        def _fail(_m):
            self._gpu_busy = False

        run_async(self, do, on_ok=_done, on_err=_fail)

    def _apply_gpu(self, gpu, jid: str) -> None:
        if jid != self._sel_job:   # 已切走，丢弃过期结果
            return
        if gpu and gpu.samples:
            self._gpu_n += 1
            self._gpu_t.append(self._gpu_n)
            self._gpu_sm.append(gpu.sm_peak)
            self._gpu_mem.append(gpu.mem_bw_peak)
            if len(self._gpu_t) > self.BUF_MAX:   # 硬上限，丢最旧
                del self._gpu_t[:-self.BUF_MAX]
                del self._gpu_sm[:-self.BUF_MAX]
                del self._gpu_mem[:-self.BUF_MAX]
            xs, ys = self._smooth_tail(self._gpu_t, self._gpu_sm)
            _, ym = self._smooth_tail(self._gpu_t, self._gpu_mem)
            self.gpu_curve.setData(xs, ys)
            self.mem_curve.setData(xs, ym)
            # 固定时间窗滚动：新点从右进、旧点左移出窗（两栏同步）
            for p in (self.gpu_plot, self.mem_plot):
                p.setXRange(self._gpu_n - self.GPU_WIN, self._gpu_n, padding=0)
            self.lbl_gpu.setText(
                f"SM 峰值 {gpu.sm_peak}% · 均值 {gpu.sm_avg}% · "
                f"显存利用率峰值 {gpu.mem_bw_peak}% · 显存占用 {gpu.fb_used_mb} MB")

    @staticmethod
    def _build_err_summary(state: str, exitcode: str, reason: str, err_tail: str) -> str:
        bits = [f"✗ {state}"]
        if exitcode and exitcode not in ("0:0",):
            code = exitcode.split(":")[0]
            hint = " (命令未找到)" if code == "127" else (
                " (OOM/被杀)" if code in ("137", "139") else "")
            bits.append(f"退出码 {exitcode}{hint}")
        if reason and reason not in ("None", ""):
            bits.append(f"原因 {reason}")
        head = " · ".join(bits)
        last = ""
        if err_tail.strip():
            lines = [l for l in err_tail.strip().splitlines() if l.strip()]
            last = "\n最后错误输出：\n" + "\n".join(lines[-4:])
        return head + last

    @staticmethod
    def _fmt_detail(d: dict) -> str:
        keys = ["JobId", "JobName", "JobState", "Reason", "RunTime", "TimeLimit",
                "Partition", "QOS", "NodeList", "NumNodes", "NumCPUs",
                "TresPerNode", "StartTime", "WorkDir", "StdOut", "StdErr"]
        lines = [f"{k:14}= {d[k]}" for k in keys if k in d]
        return "\n".join(lines) if lines else "（无详情，任务可能已结束）"

    @staticmethod
    def _smooth_tail(xs, ys, k: int = 3):
        """尾部移动平均，抹采样抖动；不引入未来值（无前瞻泄漏）。"""
        n = len(ys)
        if n < k:
            return xs, ys
        sm = []
        for i in range(n):
            lo = max(0, i - k + 1)
            sm.append(sum(ys[lo:i + 1]) / (i - lo + 1))
        return xs, sm

    def _apply_detail(self, data: dict) -> None:
        # 错误横幅
        err = data.get("err", "")
        if err:
            self.err_banner.setText(err)
            self.err_banner.setVisible(True)
        else:
            self.err_banner.setVisible(False)
        self.detail_view.setPlainText(data["detail"] or "（任务已结束，调度器不再保留详情；状态见任务表）")
        if data["log"]:
            self.log_view.setPlainText(data["log"])
        else:
            st = data.get("state", "")
            if st in ("PENDING",):
                msg = "（任务排队中，日志尚未生成）"
            elif st in ("COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY"):
                msg = ("（任务已结束，未定位到日志文件——可能日志写在非标准路径，"
                       "或已被清理。可在「文件传输」页到工作目录手动查看）")
            else:
                msg = "（暂无日志）"
            self.log_view.setPlainText(msg)
        self.lbl_logpath.setText(data["log_path"] or "")
        if data.get("state") != "RUNNING":
            self.lbl_gpu.setText("GPU：仅运行中的 GPU 任务有利用率数据")

    # ---- 取消 ----
    def _cancel_job(self) -> None:
        if not self._sel_job:
            return
        if QMessageBox.question(self, "取消任务", f"scancel {self._sel_job}？")\
                != QMessageBox.StandardButton.Yes:
            return
        jid = self._sel_job
        run_async(self, lambda: self.ctx.ssh.exec(slurm.cancel_cmd(jid)),
                  on_ok=lambda _: (self.ctx.status_message.emit(f"已取消 {jid}"),
                                   self.refresh()),
                  on_err=self._err)

    def _err(self, msg: str) -> None:
        self.ctx.status_message.emit(f"错误：{msg}")

    # ---- 主题 ----
    def apply_theme(self) -> None:
        p = theme.palette()
        for plot in (self.gpu_plot, self.mem_plot):
            plot.setBackground(p["BG_ALT"])
            for axn in ("left", "bottom"):
                ax = plot.getAxis(axn)
                ax.setTextPen(p["TEXT"])
                ax.setPen(p["TEXT_DIM"])
        self.gpu_curve.setPen(pg.mkPen(p["ACCENT"], width=2))
        self.mem_curve.setPen(pg.mkPen(p["WARN"], width=2))
        # 表格状态列重新着色
        sc = theme.state_colors()
        for r, j in enumerate(self._jobs):
            it = self.table.item(r, 2)
            if it:
                color = sc.get(j.state, p["TEXT"])
                it.setForeground(QColor(color))
