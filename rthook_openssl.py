# PyInstaller 运行时 hook：在任何模块导入前设置环境变量。
# 打包后 cryptography 带的 OpenSSL 3.0 加载 legacy provider 会失败（fatal），
# 关掉 legacy 算法即可正常跑（paramiko 默认握手不需要 legacy）。
import os

os.environ.setdefault("CRYPTOGRAPHY_OPENSSL_NO_LEGACY", "1")
