"""主窗口：顶部连接状态栏 + 四个功能标签页。"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QStatusBar, QTabWidget, QVBoxLayout, QWidget,
)

from core import config
from .app_context import AppContext
from .connection_panel import ConnectionPanel
from .jobs_panel import JobsPanel
from .transfer_panel import TransferPanel
from .submit_panel import SubmitPanel


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.ctx = AppContext()
        self.setWindowTitle(f"{config.APP_NAME} {config.APP_VERSION}")
        self.resize(1180, 760)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 8)
        root.setSpacing(10)

        root.addWidget(self._build_connbar())

        self.tabs = QTabWidget()
        self.conn_panel = ConnectionPanel(self.ctx)
        self.jobs_panel = JobsPanel(self.ctx)
        self.transfer_panel = TransferPanel(self.ctx)
        self.submit_panel = SubmitPanel(self.ctx)
        self.tabs.addTab(self.conn_panel, "连接")
        self.tabs.addTab(self.jobs_panel, "任务监控")
        self.tabs.addTab(self.transfer_panel, "文件传输")
        self.tabs.addTab(self.submit_panel, "提交任务")
        root.addWidget(self.tabs, 1)

        self.setCentralWidget(central)

        sb = QStatusBar()
        self.setStatusBar(sb)
        sb.showMessage("未连接 — 先在「连接」页选择集群")

        self.ctx.connected.connect(self._on_connected)
        self.ctx.disconnected.connect(self._on_disconnected)
        self.ctx.status_message.connect(lambda m: self.statusBar().showMessage(m))

        # 窗口显示后尝试自动连接（不阻塞 UI）
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(200, self.conn_panel.try_autoconnect)

    def _build_connbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("connbar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 8, 14, 8)

        self.dot = QLabel("●")
        self.dot.setObjectName("dot_off")
        self.conn_label = QLabel("未连接")
        lay.addWidget(self.dot)
        lay.addWidget(self.conn_label)
        lay.addStretch(1)

        self.btn_theme = QPushButton("◐ 浅色 / 深色")
        self.btn_theme.clicked.connect(self._toggle_theme)
        lay.addWidget(self.btn_theme)

        self.btn_quick_disconnect = QPushButton("断开")
        self.btn_quick_disconnect.setObjectName("danger")
        self.btn_quick_disconnect.setEnabled(False)
        self.btn_quick_disconnect.clicked.connect(self.ctx.set_disconnected)
        lay.addWidget(self.btn_quick_disconnect)
        return bar

    def _toggle_theme(self) -> None:
        from . import theme
        theme.CURRENT = "light" if theme.CURRENT == "dark" else "dark"
        from core import config
        s = config.load_settings()
        s["theme"] = theme.CURRENT
        config.save_settings(s)
        app = self.window().window()  # QApplication
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().setStyleSheet(theme.stylesheet())
        self.jobs_panel.apply_theme()
        self.statusBar().showMessage(f"已切换到{'浅色' if theme.CURRENT=='light' else '深色'}主题")

    def _on_connected(self, profile) -> None:
        self.dot.setObjectName("dot_on")
        self.dot.setStyleSheet("")  # 触发重新应用 QSS
        self.dot.style().unpolish(self.dot)
        self.dot.style().polish(self.dot)
        self.conn_label.setText(f"已连接：{profile.username}@{profile.host}")
        self.btn_quick_disconnect.setEnabled(True)
        self.tabs.setCurrentWidget(self.jobs_panel)

    def _on_disconnected(self) -> None:
        self.dot.setObjectName("dot_off")
        self.dot.style().unpolish(self.dot)
        self.dot.style().polish(self.dot)
        self.conn_label.setText("未连接")
        self.btn_quick_disconnect.setEnabled(False)

    def closeEvent(self, event) -> None:
        try:
            self.ctx.ssh.close()
        except Exception:
            pass
        super().closeEvent(event)
