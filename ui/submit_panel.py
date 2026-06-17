"""任务提交向导。

填表 → 实时预览 submit.sh → 一键写到远端并 sbatch。
连接后自动用 profile 的 account/partition/qos/workdir/python 预填。
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from core import slurm
from core.worker import run_async
from .app_context import AppContext


class SubmitPanel(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx

        root = QHBoxLayout(self)

        # ---- 左：表单 ----
        box = QGroupBox("作业参数")
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setVerticalSpacing(9)

        self.in_name = QLineEdit("job")
        self.in_account = QLineEdit()
        self.in_partition = QLineEdit()
        self.in_qos = QLineEdit()
        self.in_nodes = QSpinBox(); self.in_nodes.setRange(1, 64); self.in_nodes.setValue(1)
        self.in_ntasks = QSpinBox(); self.in_ntasks.setRange(1, 256); self.in_ntasks.setValue(1)
        self.in_cpus = QSpinBox(); self.in_cpus.setRange(1, 256); self.in_cpus.setValue(8)
        self.in_gpus = QSpinBox(); self.in_gpus.setRange(0, 16); self.in_gpus.setValue(1)
        self.in_mem = QLineEdit(); self.in_mem.setPlaceholderText("例 64G，空=不限制")
        self.in_time = QLineEdit("24:00:00")
        self.in_workdir = QLineEdit()
        self.in_workdir.setPlaceholderText("远端工作目录（cd 到此）")
        self.in_env = QLineEdit()
        self.in_env.setPlaceholderText("环境准备，例 source activate myenv")
        self.in_cmd = QPlainTextEdit()
        self.in_cmd.setPlaceholderText(
            "真正执行的命令，例：\npython train.py --config configs/exp.yaml")
        self.in_cmd.setFixedHeight(90)
        self.in_script = QLineEdit("submit.sh")
        self.in_script.setPlaceholderText("脚本写到远端的路径（相对工作目录或绝对）")

        for label, w in [
            ("作业名", self.in_name), ("account", self.in_account),
            ("分区", self.in_partition), ("QOS", self.in_qos),
            ("节点数", self.in_nodes), ("ntasks", self.in_ntasks),
            ("CPU/任务", self.in_cpus), ("GPU 数", self.in_gpus),
            ("内存", self.in_mem), ("时限", self.in_time),
            ("工作目录", self.in_workdir), ("环境准备", self.in_env),
        ]:
            form.addRow(label, w)
        form.addRow("执行命令", self.in_cmd)
        form.addRow("脚本路径", self.in_script)

        # 任何字段变 → 刷新预览
        for w in (self.in_name, self.in_account, self.in_partition, self.in_qos,
                  self.in_mem, self.in_time, self.in_workdir, self.in_env, self.in_script):
            w.textChanged.connect(self._preview)
        for w in (self.in_nodes, self.in_ntasks, self.in_cpus, self.in_gpus):
            w.valueChanged.connect(self._preview)
        self.in_cmd.textChanged.connect(self._preview)

        left = QWidget(); left.setLayout(QVBoxLayout())
        left.layout().addWidget(box)
        left.setFixedWidth(420)
        root.addWidget(left)

        # ---- 右：预览（可编辑）+ 提交 ----
        right = QVBoxLayout()
        head = QHBoxLayout()
        head.addWidget(QLabel("submit.sh（可直接编辑）"))
        head.addStretch(1)
        self.lbl_mode = QLabel("跟随表单")
        self.lbl_mode.setObjectName("hint")
        self.btn_regen = QPushButton("↻ 从表单重新生成")
        self.btn_regen.clicked.connect(self._regen)
        head.addWidget(self.lbl_mode)
        head.addWidget(self.btn_regen)
        right.addLayout(head)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(False)
        self._setting = False   # 程序性赋值时为 True，避免被当成手动编辑
        self._manual = False    # 用户手改过脚本 → 表单不再覆盖，提交用脚本原文
        self.preview.textChanged.connect(self._on_preview_edited)
        right.addWidget(self.preview, 1)
        act = QHBoxLayout()
        self.lbl_status = QLabel("未连接时只能预览")
        self.lbl_status.setObjectName("hint")
        self.btn_submit = QPushButton("写入远端并 sbatch 提交")
        self.btn_submit.setObjectName("primary")
        self.btn_submit.clicked.connect(self._submit)
        act.addWidget(self.lbl_status)
        act.addStretch(1)
        act.addWidget(self.btn_submit)
        right.addLayout(act)
        root.addLayout(right, 1)

        self.ctx.connected.connect(self._on_connected)
        self.ctx.disconnected.connect(lambda: self.btn_submit.setEnabled(False))
        self.btn_submit.setEnabled(False)
        self._preview()

    def _on_connected(self, profile) -> None:
        self.btn_submit.setEnabled(True)
        if not self.in_account.text(): self.in_account.setText(profile.slurm_account)
        if not self.in_partition.text(): self.in_partition.setText(profile.partition)
        if not self.in_qos.text(): self.in_qos.setText(profile.qos)
        if not self.in_workdir.text(): self.in_workdir.setText(profile.default_remote_dir)
        if profile.python_path and not self.in_env.text():
            self.in_env.setText(f"# 使用绝对 python：{profile.python_path}")
        self.lbl_status.setText("已连接，可提交")

    def _spec(self) -> slurm.SbatchSpec:
        return slurm.SbatchSpec(
            job_name=self.in_name.text().strip() or "job",
            account=self.in_account.text().strip(),
            partition=self.in_partition.text().strip(),
            qos=self.in_qos.text().strip(),
            nodes=self.in_nodes.value(),
            ntasks=self.in_ntasks.value(),
            cpus_per_task=self.in_cpus.value(),
            gpus=self.in_gpus.value(),
            mem=self.in_mem.text().strip(),
            time_limit=self.in_time.text().strip(),
            workdir=self.in_workdir.text().strip(),
            env_setup=self.in_env.text().strip(),
            command=self.in_cmd.toPlainText().strip(),
        )

    def _preview(self) -> None:
        if self._manual:        # 用户已手改脚本，不覆盖
            return
        self._setting = True
        self.preview.setPlainText(slurm.build_sbatch(self._spec()))
        self._setting = False

    def _on_preview_edited(self) -> None:
        if self._setting:
            return
        self._manual = True
        self.lbl_mode.setText("手动编辑（提交用脚本原文）")

    def _regen(self) -> None:
        self._manual = False
        self.lbl_mode.setText("跟随表单")
        self._preview()

    def _script_path(self) -> str:
        path = self.in_script.text().strip() or "submit.sh"
        wd = self.in_workdir.text().strip()
        if not path.startswith("/") and wd:
            path = wd.rstrip("/") + "/" + path
        return path

    def _submit(self) -> None:
        spec = self._spec()
        # 提交用预览框里的真实内容（含手动改动），所见即所得
        content = self.preview.toPlainText().strip()
        if not content or content == "#!/bin/bash":
            QMessageBox.warning(self, "脚本为空", "submit.sh 内容为空，填执行命令或直接编辑脚本。")
            return
        rpath = self._script_path()
        if QMessageBox.question(
                self, "确认提交",
                f"将写入远端：\n{rpath}\n并执行 sbatch。继续？")\
                != QMessageBox.StandardButton.Yes:
            return
        self.btn_submit.setEnabled(False)
        self.lbl_status.setText("提交中…")

        def do():
            # 确保 logs 目录存在
            wd = spec.workdir
            if wd:
                self.ctx.ssh.exec(f"mkdir -p {wd.rstrip('/')}/logs")
            return slurm.submit_script(self.ctx.ssh, rpath, content)

        run_async(self, do, on_ok=self._on_submitted, on_err=self._on_err)

    def _on_submitted(self, res) -> None:
        self.btn_submit.setEnabled(True)
        if not res.ok:
            self.lbl_status.setText("提交失败")
            QMessageBox.critical(self, "提交失败", res.err or res.out or "未知错误")
            return
        jid = slurm.parse_submitted_job_id(res.out)
        self.lbl_status.setText(f"已提交：Job {jid}" if jid else res.out)
        QMessageBox.information(
            self, "提交成功",
            f"{res.out}\n\n到「任务监控」页查看进度。")
        self.ctx.status_message.emit(f"已提交 {res.out}")

    def _on_err(self, msg: str) -> None:
        self.btn_submit.setEnabled(True)
        self.lbl_status.setText("提交失败")
        QMessageBox.critical(self, "提交失败", msg)
