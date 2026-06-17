"""把阻塞的 SSH/SFTP 调用丢到线程池，结果用信号回主线程更新 UI。

用法:
    run_async(self, lambda: ssh.exec("squeue ..."),
              on_ok=self._fill_table, on_err=self._show_error)
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal


class _Signals(QObject):
    ok = pyqtSignal(object)
    err = pyqtSignal(str)
    progress = pyqtSignal(int, int)


class _Task(QRunnable):
    def __init__(self, fn: Callable[..., Any], signals: _Signals,
                 with_progress: bool = False):
        super().__init__()
        self._fn = fn
        self._signals = signals
        self._with_progress = with_progress

    def run(self) -> None:
        try:
            if self._with_progress:
                result = self._fn(self._signals.progress.emit)
            else:
                result = self._fn()
            self._signals.ok.emit(result)
        except Exception as e:  # 全部异常回主线程，绝不让线程崩掉吞掉错误
            self._signals.err.emit(str(e))


_pool = QThreadPool.globalInstance()


def run_async(parent: QObject,
              fn: Callable[..., Any],
              on_ok: Optional[Callable[[Any], None]] = None,
              on_err: Optional[Callable[[str], None]] = None) -> _Signals:
    """在全局线程池跑 fn；on_ok/on_err 在主线程触发。返回 signals 以便接 progress。"""
    sig = _Signals()
    # 绑定到 parent，防止被 GC（Qt 信号需活引用）
    if not hasattr(parent, "_async_sigs"):
        parent._async_sigs = []  # type: ignore[attr-defined]
    parent._async_sigs.append(sig)  # type: ignore[attr-defined]

    def _cleanup(*_):
        try:
            parent._async_sigs.remove(sig)  # type: ignore[attr-defined]
        except (ValueError, AttributeError):
            pass

    if on_ok:
        sig.ok.connect(on_ok)
    if on_err:
        sig.err.connect(on_err)
    sig.ok.connect(_cleanup)
    sig.err.connect(_cleanup)

    _pool.start(_Task(fn, sig))
    return sig


def run_with_progress(parent: QObject,
                      fn: Callable[[Callable[[int, int], None]], Any],
                      on_ok: Optional[Callable[[Any], None]] = None,
                      on_err: Optional[Callable[[str], None]] = None,
                      on_progress: Optional[Callable[[int, int], None]] = None) -> _Signals:
    """fn 接收一个 progress(transferred, total) 回调，可用于 SFTP put/get。"""
    sig = _Signals()
    if not hasattr(parent, "_async_sigs"):
        parent._async_sigs = []  # type: ignore[attr-defined]
    parent._async_sigs.append(sig)  # type: ignore[attr-defined]

    def _cleanup(*_):
        try:
            parent._async_sigs.remove(sig)  # type: ignore[attr-defined]
        except (ValueError, AttributeError):
            pass

    if on_progress:
        sig.progress.connect(on_progress)
    if on_ok:
        sig.ok.connect(on_ok)
    if on_err:
        sig.err.connect(on_err)
    sig.ok.connect(_cleanup)
    sig.err.connect(_cleanup)

    _pool.start(_Task(fn, sig, with_progress=True))
    return sig
