"""HPC Companion 入口。"""
from __future__ import annotations

import os
# 必须在 cryptography（paramiko 依赖）导入前设置：打包后 OpenSSL 3.0 legacy
# provider 加载失败会 fatal 崩溃，关掉 legacy 算法即可（握手不需要它）。
os.environ.setdefault("CRYPTOGRAPHY_OPENSSL_NO_LEGACY", "1")

import sys

from PyQt6.QtWidgets import QApplication

from core import config
from ui import theme
from ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setOrganizationName(config.ORG)
    theme.CURRENT = config.load_settings().get("theme", "dark")
    app.setStyleSheet(theme.stylesheet())

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
