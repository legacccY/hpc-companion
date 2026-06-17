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

## 🚀 快速开始

```bash
pip install -r requirements.txt
python main.py
```

> [!NOTE]
> **PyQt6 版本锁定 `6.6.1`**。`6.7+` 在部分 Anaconda / 旧 MSVC 运行库环境会报
> `DLL load failed while importing QtCore`，换环境前先确认。

## 📦 打包成 exe

```bash
pip install pyinstaller
pyinstaller build.spec --noconfirm
# 产物：dist/HPC-Companion.exe（单文件，可直接发给同学）
```

`build.spec` 已处理 paramiko / keyring / cryptography 的隐式导入与 OpenSSL 兼容问题。
首次打包后，建议在一台没装 Python 的干净机器上验证：能启动、能连接、密码能存进凭据库。

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
