"""深色 / 浅色双主题。QSS 由调色板模板生成。"""

PALETTES = {
    "dark": {
        "BG": "#1b1d23", "BG_ALT": "#22252d", "BG_INPUT": "#2a2e38",
        "BORDER": "#343845", "TEXT": "#d7dae0", "TEXT_DIM": "#8b909c",
        "ACCENT": "#39b8a0", "ACCENT_HOVER": "#45cdb3", "SEL_TEXT": "#0c1412",
        "DANGER": "#e05a5a", "WARN": "#d9a441", "OK": "#3fbf6f",
        "TAB_BG": "#262a33",
    },
    "light": {
        "BG": "#eef0f4", "BG_ALT": "#ffffff", "BG_INPUT": "#ffffff",
        "BORDER": "#cdd2dc", "TEXT": "#1f2330", "TEXT_DIM": "#6c727f",
        "ACCENT": "#138a76", "ACCENT_HOVER": "#1aa78e", "SEL_TEXT": "#ffffff",
        "DANGER": "#cf3b3b", "WARN": "#a9761a", "OK": "#2c9b51",
        "TAB_BG": "#e3e6ec",
    },
}

# 当前主题名（模块级，供各面板读取）
CURRENT = "dark"


def palette(name: str | None = None) -> dict:
    return PALETTES.get(name or CURRENT, PALETTES["dark"])


def state_colors(name: str | None = None) -> dict:
    p = palette(name)
    return {
        "RUNNING": p["OK"], "PENDING": p["WARN"], "COMPLETING": p["ACCENT"],
        "COMPLETED": p["TEXT_DIM"], "FAILED": p["DANGER"], "CANCELLED": p["DANGER"],
        "TIMEOUT": p["DANGER"], "OUT_OF_MEMORY": p["DANGER"],
    }


def stylesheet(name: str | None = None) -> str:
    p = palette(name)
    return f"""
* {{
    font-family: "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
    font-size: 13px; color: {p['TEXT']}; outline: none;
}}
QMainWindow, QWidget {{ background: {p['BG']}; }}

/* 外层标签页 */
QTabWidget::pane {{ border: 1px solid {p['BORDER']}; border-radius: 6px; top: -1px; background: {p['BG_ALT']}; }}
QTabBar::tab {{
    background: {p['TAB_BG']}; color: {p['TEXT_DIM']};
    padding: 8px 18px; margin-right: 3px;
    border: 1px solid {p['BORDER']}; border-bottom: 2px solid transparent;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
}}
QTabBar::tab:selected {{
    background: {p['BG_ALT']}; color: {p['ACCENT']}; font-weight: 600;
    border-bottom: 2px solid {p['ACCENT']};
}}
QTabBar::tab:hover:!selected {{ color: {p['TEXT']}; background: {p['BG_INPUT']}; }}

/* 按钮 */
QPushButton {{
    background: {p['BG_INPUT']}; border: 1px solid {p['BORDER']};
    border-radius: 6px; padding: 7px 16px; color: {p['TEXT']};
}}
QPushButton:hover {{ border-color: {p['ACCENT']}; }}
QPushButton:pressed {{ background: {p['BORDER']}; }}
QPushButton:disabled {{ color: {p['TEXT_DIM']}; border-color: {p['BORDER']}; }}
QPushButton#primary {{ background: {p['ACCENT']}; border-color: {p['ACCENT']}; color: {p['SEL_TEXT']}; font-weight: 600; }}
QPushButton#primary:hover {{ background: {p['ACCENT_HOVER']}; border-color: {p['ACCENT_HOVER']}; }}
QPushButton#danger {{ color: {p['DANGER']}; }}
QPushButton#danger:hover {{ border-color: {p['DANGER']}; }}

/* 输入 */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {{
    background: {p['BG_INPUT']}; border: 1px solid {p['BORDER']};
    border-radius: 6px; padding: 6px 8px; selection-background-color: {p['ACCENT']};
    selection-color: {p['SEL_TEXT']};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {p['ACCENT']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {p['BG_INPUT']}; border: 1px solid {p['BORDER']};
    selection-background-color: {p['ACCENT']}; selection-color: {p['SEL_TEXT']};
}}
QPlainTextEdit, QTextEdit {{ font-family: "Cascadia Mono", "Consolas", monospace; }}
QCheckBox {{ color: {p['TEXT']}; }}

/* 列表 / 表格 / 树 */
QTableView, QTreeView, QListView, QTableWidget, QTreeWidget, QListWidget {{
    background: {p['BG_ALT']}; border: 1px solid {p['BORDER']}; border-radius: 6px;
    gridline-color: {p['BORDER']}; alternate-background-color: {p['BG_INPUT']};
}}
QTableView::item:selected, QTreeView::item:selected, QListView::item:selected {{
    background: {p['ACCENT']}; color: {p['SEL_TEXT']};
}}
QHeaderView::section {{
    background: {p['BG_INPUT']}; color: {p['TEXT_DIM']}; padding: 6px 8px;
    border: none; border-right: 1px solid {p['BORDER']}; border-bottom: 1px solid {p['BORDER']};
}}

/* 分组框 */
QGroupBox {{ border: 1px solid {p['BORDER']}; border-radius: 8px; margin-top: 14px; padding-top: 10px; font-weight: 600; color: {p['TEXT']}; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 5px; }}

QLabel#hint {{ color: {p['TEXT_DIM']}; }}
QStatusBar {{ background: {p['BG_ALT']}; color: {p['TEXT_DIM']}; border-top: 1px solid {p['BORDER']}; }}

QProgressBar {{ background: {p['BG_INPUT']}; border: 1px solid {p['BORDER']}; border-radius: 6px; text-align: center; height: 18px; color: {p['TEXT']}; }}
QProgressBar::chunk {{ background: {p['ACCENT']}; border-radius: 5px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {p['BORDER']}; border-radius: 5px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: {p['TEXT_DIM']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{ background: {p['BORDER']}; border-radius: 5px; min-width: 28px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}

QFrame#connbar {{ background: {p['BG_ALT']}; border: 1px solid {p['BORDER']}; border-radius: 8px; }}
QLabel#dot_off {{ color: {p['DANGER']}; font-size: 16px; }}
QLabel#dot_on {{ color: {p['OK']}; font-size: 16px; }}
"""
