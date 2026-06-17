"""连接 / Profile 管理面板。

左：已存集群列表 + 新建/删除。右：编辑表单 + 连接按钮。
密码经 keyring 加密存储；切预设可一键套用常用集群字段。
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from core import config
from core.profiles import Profile
from core.ssh_client import AuthError, NetworkError, SSHError
from core.worker import run_async
from .app_context import AppContext


class ConnectionPanel(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self._connecting = False

        root = QHBoxLayout(self)
        root.setSpacing(12)

        # ---- 左侧：profile 列表 ----
        left = QVBoxLayout()
        left.addWidget(QLabel("已保存的集群"))
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._on_select)
        left.addWidget(self.list, 1)
        btns = QHBoxLayout()
        self.btn_new = QPushButton("新建")
        self.btn_del = QPushButton("删除")
        self.btn_del.setObjectName("danger")
        self.btn_new.clicked.connect(self._new_profile)
        self.btn_del.clicked.connect(self._delete_profile)
        btns.addWidget(self.btn_new)
        btns.addWidget(self.btn_del)
        left.addLayout(btns)
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(240)
        root.addWidget(lw)

        # ---- 右侧：编辑表单 ----
        form_box = QGroupBox("连接配置")
        form = QFormLayout(form_box)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setVerticalSpacing(10)

        self.preset = QComboBox()
        self.preset.addItem("（不套用预设）")
        for name in config.CLUSTER_PRESETS:
            self.preset.addItem(name)
        self.preset.currentTextChanged.connect(self._apply_preset)

        self.in_name = QLineEdit()
        self.in_host = QLineEdit()
        self.in_port = QSpinBox()
        self.in_port.setRange(1, 65535)
        self.in_port.setValue(22)
        self.in_user = QLineEdit()
        self.in_auth = QComboBox()
        self.in_auth.addItems(["password", "key"])
        self.in_auth.currentTextChanged.connect(self._toggle_auth)
        self.in_pass = QLineEdit()
        self.in_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.in_pass.setPlaceholderText("留空=用已保存密码")
        self.in_key = QLineEdit()
        self.in_key.setPlaceholderText("私钥文件路径（auth=key 时）")
        self.in_account = QLineEdit()
        self.in_partition = QLineEdit()
        self.in_qos = QLineEdit()
        self.in_remote = QLineEdit()
        self.in_remote.setPlaceholderText("默认远端工作目录，例 /home/<user>/work")
        self.in_python = QLineEdit()
        self.in_python.setPlaceholderText("远端 python 绝对路径（提交脚本用，可空）")

        form.addRow("套用预设", self.preset)
        form.addRow("名称 *", self.in_name)
        form.addRow("主机 *", self.in_host)
        form.addRow("端口", self.in_port)
        form.addRow("用户名 *", self.in_user)
        form.addRow("认证方式", self.in_auth)
        form.addRow("密码", self.in_pass)
        form.addRow("私钥路径", self.in_key)
        form.addRow("SLURM account", self.in_account)
        form.addRow("分区 partition", self.in_partition)
        form.addRow("QOS", self.in_qos)
        form.addRow("默认远端目录", self.in_remote)
        form.addRow("远端 python", self.in_python)

        self.vpn_hint = QLabel("")
        self.vpn_hint.setObjectName("hint")
        self.vpn_hint.setWordWrap(True)
        form.addRow("", self.vpn_hint)

        self.keyring_hint = QLabel(
            "密码加密存于系统凭据库" if self.ctx.store.keyring_available
            else "⚠ 系统凭据库不可用，密码仅本次会话内存保存（重启需重填）"
        )
        self.keyring_hint.setObjectName("hint")
        form.addRow("", self.keyring_hint)

        action = QHBoxLayout()
        self.chk_autoconnect = QCheckBox("下次启动自动连接此集群")
        from core import config as _cfg
        self.chk_autoconnect.setChecked(
            bool(_cfg.load_settings().get("auto_connect_profile")))
        self.btn_save = QPushButton("保存")
        self.btn_connect = QPushButton("保存并连接")
        self.btn_connect.setObjectName("primary")
        self.btn_save.clicked.connect(self._save)
        self.btn_connect.clicked.connect(self._save_and_connect)
        action.addWidget(self.chk_autoconnect)
        action.addStretch(1)
        action.addWidget(self.btn_save)
        action.addWidget(self.btn_connect)

        right = QVBoxLayout()
        right.addWidget(form_box, 1)
        right.addLayout(action)
        rw = QWidget()
        rw.setLayout(right)
        root.addWidget(rw, 1)

        self._toggle_auth(self.in_auth.currentText())
        self._refresh_list()

    # ---- 列表 ----
    def _refresh_list(self) -> None:
        self.list.clear()
        for p in self.ctx.store.list():
            QListWidgetItem(p.name, self.list)
        # 有已存集群时默认选中第一条，表单立即填好，无需手点
        if self.list.count() > 0 and self.list.currentRow() < 0:
            self.list.setCurrentRow(0)

    def _on_select(self, cur: QListWidgetItem, _prev=None) -> None:
        if cur is None:
            return
        p = self.ctx.store.get(cur.text())
        if p is None:
            return
        self.in_name.setText(p.name)
        self.in_host.setText(p.host)
        self.in_port.setValue(p.port or 22)
        self.in_user.setText(p.username)
        self.in_auth.setCurrentText(p.auth_method)
        self.in_key.setText(p.key_path)
        self.in_account.setText(p.slurm_account)
        self.in_partition.setText(p.partition)
        self.in_qos.setText(p.qos)
        self.in_remote.setText(p.default_remote_dir)
        self.in_python.setText(p.python_path)
        self.in_pass.clear()
        self.vpn_hint.setText(p.vpn_note)

    def _new_profile(self) -> None:
        self.list.clearSelection()
        for w in (self.in_name, self.in_host, self.in_user, self.in_key,
                  self.in_account, self.in_partition, self.in_qos,
                  self.in_remote, self.in_python, self.in_pass):
            w.clear()
        self.in_port.setValue(22)
        self.in_auth.setCurrentText("password")
        self.vpn_hint.setText("")

    def _delete_profile(self) -> None:
        cur = self.list.currentItem()
        if cur is None:
            return
        if QMessageBox.question(self, "删除", f"删除集群「{cur.text()}」？")\
                == QMessageBox.StandardButton.Yes:
            self.ctx.store.delete(cur.text())
            self._refresh_list()
            self._new_profile()

    # ---- 预设 / 认证切换 ----
    def _apply_preset(self, name: str) -> None:
        preset = config.CLUSTER_PRESETS.get(name)
        if not preset:
            return
        self.in_host.setText(preset["host"])
        self.in_port.setValue(preset["port"])
        self.in_account.setText(preset["slurm_account"])
        self.in_partition.setText(preset["partition"])
        self.in_qos.setText(preset["qos"])
        self.in_remote.setText(preset["default_remote_dir"])
        self.in_python.setText(preset["python_path"])
        self.vpn_hint.setText(preset["vpn_note"])
        if not self.in_name.text():
            self.in_name.setText(name)

    def _toggle_auth(self, method: str) -> None:
        is_key = method == "key"
        self.in_key.setEnabled(is_key)
        self.in_pass.setPlaceholderText(
            "私钥口令（可空）" if is_key else "留空=用已保存密码"
        )

    # ---- 收集表单 ----
    def _collect(self) -> Profile | None:
        name = self.in_name.text().strip()
        host = self.in_host.text().strip()
        user = self.in_user.text().strip()
        if not (name and host and user):
            QMessageBox.warning(self, "缺字段", "名称 / 主机 / 用户名 为必填。")
            return None
        return Profile(
            name=name, host=host, port=self.in_port.value(), username=user,
            auth_method=self.in_auth.currentText(), key_path=self.in_key.text().strip(),
            slurm_account=self.in_account.text().strip(),
            partition=self.in_partition.text().strip(),
            qos=self.in_qos.text().strip(),
            default_remote_dir=self.in_remote.text().strip(),
            python_path=self.in_python.text().strip(),
            vpn_note=self.vpn_hint.text().strip(),
        )

    def _save(self) -> Profile | None:
        p = self._collect()
        if p is None:
            return None
        pw = self.in_pass.text()
        self.ctx.store.upsert(p, password=pw if pw else None)
        self._refresh_list()
        # 选中刚保存的
        items = self.list.findItems(p.name, Qt.MatchFlag.MatchExactly)
        if items:
            self.list.setCurrentItem(items[0])
        self.ctx.status_message.emit(f"已保存集群「{p.name}」")
        return p

    # ---- 连接 ----
    def _save_and_connect(self) -> None:
        if self._connecting:
            return
        p = self._save()
        if p is None:
            return
        pw = self.in_pass.text() or self.ctx.store.get_password(p)
        if pw is None and p.auth_method == "password":
            QMessageBox.warning(self, "缺密码", "首次连接请填写密码。")
            return

        self._connecting = True
        self.btn_connect.setEnabled(False)
        self.btn_connect.setText("连接中…")
        self.ctx.status_message.emit(f"正在连接 {p.host} …")

        def do():
            self.ctx.ssh.connect(p, password=pw)
            return p

        run_async(self, do, on_ok=self._on_ok, on_err=self._on_err)

    def _on_ok(self, p: Profile) -> None:
        self._connecting = False
        self.btn_connect.setEnabled(True)
        self.btn_connect.setText("保存并连接")
        # 记忆自动连接选择
        from core import config as _cfg
        s = _cfg.load_settings()
        s["auto_connect_profile"] = p.name if self.chk_autoconnect.isChecked() else ""
        _cfg.save_settings(s)
        self.ctx.set_connected(p)

    def try_autoconnect(self) -> None:
        """启动时调用：若设了自动连接且密码已存，则免登录直接连。"""
        from core import config as _cfg
        name = _cfg.load_settings().get("auto_connect_profile")
        if not name:
            return
        p = self.ctx.store.get(name)
        if p is None:
            return
        pw = self.ctx.store.get_password(p)
        if pw is None and p.auth_method == "password":
            return
        items = self.list.findItems(name, Qt.MatchFlag.MatchExactly)
        if items:
            self.list.setCurrentItem(items[0])
        self._connecting = True
        self.btn_connect.setEnabled(False)
        self.btn_connect.setText("自动连接中…")
        self.ctx.status_message.emit(f"自动连接 {p.host} …")
        run_async(self, lambda: (self.ctx.ssh.connect(p, password=pw), p)[1],
                  on_ok=self._on_ok, on_err=self._on_err)

    def _on_err(self, msg: str) -> None:
        self._connecting = False
        self.btn_connect.setEnabled(True)
        self.btn_connect.setText("保存并连接")
        self.ctx.status_message.emit("连接失败")
        QMessageBox.critical(self, "连接失败", msg)
