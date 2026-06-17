<div align="center">

# 🖥️ HPC Companion

### 给学生用的 SLURM 集群图形客户端

把繁琐的 SSH 登录、`sbatch` 提交、任务监控、文件传输，<br>
收进一个**双击即用**的桌面程序 —— 全程不用记一条命令。

<br>

![License](https://img.shields.io/badge/License-MIT-green.svg)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)
![PyQt6](https://img.shields.io/badge/GUI-PyQt6-41cd52.svg)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)

📖 **新手必读 → [图文使用教程](docs/使用教程.md)**

<br>

<img src="docs/images/03_gpu显存.png" alt="GPU / 显存实时曲线" width="80%">

</div>

---

## ✨ 特性

- 🔌 **多集群管理** —— profile 一键切换，常用 GPU 集群字段自带预设
- 🔒 **密码安全** —— 经系统凭据库加密存储，绝不明文落盘
- 📊 **任务监控** —— `squeue` / `sacct` 融合，状态着色、失败红横幅、一键取消
- 📈 **实时显卡曲线** —— GPU + 显存双栏，任务管理器式滚动 / 填充 / 平滑
- 📂 **双栏文件传输** —— 多选上传 / 下载，带进度、断点续传
- 📝 **可视化提交** —— 填表实时生成 `submit.sh`，可手改，一键 `sbatch`
- ⚡ **永不卡顿** —— 所有网络操作走后台线程，界面始终流畅
- 📦 **单文件 exe** —— 打包后双击即用，无需目标机装 Python

---

## 🖼️ 截图

| 任务监控（状态着色） | GPU / 显存双栏曲线 |
| :---: | :---: |
| ![任务监控](docs/images/02_任务监控.png) | ![GPU 显存](docs/images/03_gpu显存.png) |

<details>
<summary>📸 更多截图（连接 · 文件传输 · 提交任务）</summary>

<br>

**连接 / 集群管理**

![连接](docs/images/01_连接.png)

**文件传输**

![文件传输](docs/images/04_文件传输.png)

**提交任务**

![提交任务](docs/images/05_提交任务.png)

</details>

---

## ⬇️ 下载

到 [**Releases**](../../releases) 下载开箱即用的版本（由 GitHub Actions 自动构建）：

- **Windows** —— `HPC-Companion-windows.exe`，双击运行
- **macOS** —— `HPC-Companion-macos.zip`，解压得到 `HPC Companion.app` 拖进「应用程序」

> macOS 首次打开若提示「无法验证开发者」，右键 App → 打开，或在「系统设置 → 隐私与安全性」放行（应用未做 Apple 签名）。

## 🚀 源码运行

```bash
pip install -r requirements.txt
python main.py
```

支持 **Windows / macOS / Linux**（Python 3.10+）。

> [!NOTE]
> **PyQt6 版本锁定 `6.6.1`**。`6.7+` 在部分 Anaconda / 旧 MSVC 运行库环境会报
> `DLL load failed while importing QtCore`，换环境前先确认。

## 📦 自己打包

同一份 `build.spec` 跨平台，在对应系统上运行即可：

```bash
pip install pyinstaller
pyinstaller build.spec --noconfirm
```

| 系统 | 产物 |
| --- | --- |
| Windows | `dist/HPC-Companion.exe`（单文件） |
| macOS | `dist/HPC Companion.app`（拖进「应用程序」即可） |
| Linux | `dist/HPC-Companion`（单文件可执行） |

`build.spec` 按平台收 keyring 后端、处理 paramiko / cryptography 隐式导入与 OpenSSL 兼容；
macOS 额外包成 `.app`（Retina、跟随系统深 / 浅色）。无需自己买 Mac —— 推一个 `v*` tag，
GitHub Actions 会在云端的 Windows / macOS runner 上自动打包并发布到 Releases。

## 🔒 安全设计

- 密码存系统凭据库（Windows 凭据管理器 / macOS Keychain），`profiles.json` 只存非敏感字段，**绝不明文落盘**。
- 凭据库不可用时退化为「本次运行内存保存」，重启需重填——同样不写明文到硬盘。

## 🧪 测试

```bash
python -m pytest tests/ -q     # SLURM 解析 / 生成纯函数单测
```

## 🏗️ 架构

```
main.py                 入口
core/
  config.py             路径常量 + 集群预设
  profiles.py           profile CRUD + keyring 密码读写
  ssh_client.py         paramiko SSH/SFTP 唯一出口（线程安全）
  slurm.py              squeue/scontrol/sinfo 解析 + sbatch 生成（纯函数，可测）
  worker.py             QThreadPool 异步执行器（含进度回调），SSH 调用不卡 UI
ui/
  theme.py              深 / 浅双主题 QSS
  app_context.py        共享 SSH 连接 + 连接状态信号
  main_window.py        标签壳 + 顶部连接状态条
  connection_panel.py   连接 / profile 管理
  jobs_panel.py         任务监控（表格 / 日志 / GPU·显存曲线）
  transfer_panel.py     SFTP 双栏传输
  submit_panel.py       提交向导
```

> 所有阻塞的 SSH/SFTP 调用都走 `core.worker` 丢到线程池，结果用 Qt 信号回主线程，界面始终不冻结。

## 🗺️ Roadmap

计划与已知问题见 [`TODO.md`](TODO.md)。欢迎 issue / PR。

---

<div align="center">

📄 [MIT License](LICENSE) © 2026 legacccY

</div>
