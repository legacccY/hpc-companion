# Roadmap / 已知问题

## 计划中

- 连上真实集群、选中运行中的 GPU 任务，目视确认两栏曲线（GPU / 显存）滚动、填充、平滑表现。
- 在没装 Python 的干净机器上验证打包好的 exe：能启动、能连接、密码能存进系统凭据库。
- 给 exe 加应用图标（`build.spec` 的 `icon` 字段）。
- 可选：连接 / 提交支持更多 SLURM 字段（`--nodelist`、`--exclude`、数组作业等）。

## 已知问题

- Windows 上偶尔残留一个空闲的 ~39 MB Python 子进程（疑似子进程启动副产物），不影响使用，待查。

## 已完成

- 核心后端：paramiko SSH/SFTP（30s 保活）+ SLURM 解析 / `sbatch` 生成 + keyring 密码 + QThreadPool 异步。
- 四面板：连接（profile / 自动连接 / 预设）· 任务监控 · 文件传输（双栏 / 断点续传 / 速度 / ETA）· 提交向导（可编辑脚本）。
- 任务监控：`squeue` + `sacct` 融合（结束任务不消失）· 历史范围 · 失败红横幅（退出码 + err 尾）· 日志自动定位 + 缓存 · 深 / 浅主题。
- GPU / 显存：两栏实时曲线（任务管理器式滚动 / 填充 / 平滑）· Y 锁 0–100 · 可见时才采样 · 缓冲上限防内存堆积。
- 打包：PyInstaller 单文件 exe（含 OpenSSL 兼容 runtime hook）。
- 图文教程：`docs/使用教程.md` + `docs/images/`。
