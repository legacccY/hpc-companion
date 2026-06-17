"""SLURM 命令构造与输出解析。纯函数 + 薄封装，便于测试。"""
from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from typing import Optional

from .ssh_client import SSHClient, ExecResult


@dataclass
class Job:
    job_id: str
    name: str
    state: str
    time: str
    nodes: str
    reason: str
    partition: str = ""


# squeue 字段用 | 分隔，避免空格切错（任务名/原因可能含空格）
_SQUEUE_FMT = "%i|%j|%T|%M|%D|%R|%P"


def parse_squeue(out: str) -> list[Job]:
    jobs: list[Job] = []
    for line in out.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("JOBID"):
            continue
        parts = line.split("|")
        if len(parts) < 6:
            continue
        jobs.append(Job(
            job_id=parts[0].strip(),
            name=parts[1].strip(),
            state=parts[2].strip(),
            time=parts[3].strip(),
            nodes=parts[4].strip(),
            reason=parts[5].strip(),
            partition=parts[6].strip() if len(parts) > 6 else "",
        ))
    return jobs


def queue_cmd(username: str) -> str:
    return f"squeue -u {shlex.quote(username)} --noheader --format={shlex.quote(_SQUEUE_FMT)}"


def cancel_cmd(job_id: str) -> str:
    return f"scancel {shlex.quote(job_id)}"


def sacct_cmd(username: str, days: int = 0) -> str:
    """已结束任务历史（squeue 看不到结束的，靠这个补）。-X 只看作业不看子步骤。
    days<=0 表示今日；否则回看 N 天（日期在远端 shell 算）。"""
    since = "today" if days <= 0 else f"$(date -d '{days} days ago' '+%Y-%m-%d')"
    fmt = "JobID,JobName,State,Elapsed,NNodes,ExitCode"
    return (f"sacct -u {shlex.quote(username)} -S {since} -X -P -n "
            f"--format={fmt}")


def parse_sacct(out: str) -> list[Job]:
    jobs: list[Job] = []
    for line in out.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) < 6:
            continue
        jid = parts[0].strip()
        if "." in jid:           # 跳过 .batch/.extern 子步骤
            continue
        state = parts[2].strip().split()[0]   # "CANCELLED by 123" -> CANCELLED
        jobs.append(Job(
            job_id=jid, name=parts[1].strip(), state=state,
            time=parts[3].strip(), nodes=parts[4].strip(),
            reason=f"ExitCode {parts[5].strip()}",
        ))
    return jobs


def detail_cmd(job_id: str) -> str:
    return f"scontrol show job {shlex.quote(job_id)}"


def partition_info_cmd(partition: str) -> str:
    if partition:
        return f"sinfo -p {shlex.quote(partition)} --format='%P|%a|%T|%D|%N'"
    return "sinfo --format='%P|%a|%T|%D|%N'"


def parse_scontrol(out: str) -> dict[str, str]:
    """scontrol show job 输出解析为 key=value 字典。"""
    d: dict[str, str] = {}
    for token in out.split():
        if "=" in token:
            k, _, v = token.partition("=")
            d[k] = v
    return d


# ---- GPU 利用率 ----
def gpu_dmon_cmd(job_id: str, samples: int = 8) -> str:
    """在 job 所在节点上跑 nvidia-smi dmon 采样。"""
    return (f"srun --overlap --jobid={shlex.quote(job_id)} "
            f"nvidia-smi dmon -s um -c {samples} 2>&1")


@dataclass
class GpuSnapshot:
    sm_peak: int = 0
    sm_avg: int = 0
    mem_bw_peak: int = 0
    fb_used_mb: int = 0
    samples: int = 0
    raw: str = ""


def parse_gpu_dmon(raw: str) -> GpuSnapshot:
    """解析 nvidia-smi dmon -s um：Idx sm% mem% enc dec jpg ofa fb bar1 ccpm。"""
    sm, bw, fb = [], [], 0
    for ln in raw.splitlines():
        ln = ln.strip()
        if ln.startswith("#") or not ln:
            continue
        parts = ln.split()
        if len(parts) >= 8:
            try:
                sm.append(int(parts[1]))
                bw.append(int(parts[2]))
                fb = int(parts[7])
            except ValueError:
                continue
    if not sm:
        return GpuSnapshot(raw=raw[:400])
    return GpuSnapshot(
        sm_peak=max(sm), sm_avg=sum(sm) // len(sm),
        mem_bw_peak=max(bw) if bw else 0,
        fb_used_mb=fb, samples=len(sm), raw=raw[:400],
    )


# ---- sbatch 脚本生成 ----
@dataclass
class SbatchSpec:
    job_name: str = "job"
    account: str = ""
    partition: str = ""
    qos: str = ""
    nodes: int = 1
    ntasks: int = 1
    cpus_per_task: int = 8
    gpus: int = 1
    mem: str = ""              # 例 "64G"，空=不设
    time_limit: str = "24:00:00"
    workdir: str = ""
    output: str = ""          # 默认 logs/%j.out
    error: str = ""           # 默认 logs/%j.err
    env_setup: str = ""       # 例 source activate 或绝对 python 路径前置
    command: str = ""         # 真正跑的命令


def build_sbatch(spec: SbatchSpec) -> str:
    L = ["#!/bin/bash"]

    def sb(flag: str, val: str):
        if val:
            L.append(f"#SBATCH {flag}={val}")

    sb("--job-name", spec.job_name)
    sb("--account", spec.account)
    sb("--partition", spec.partition)
    sb("--qos", spec.qos)
    L.append(f"#SBATCH --nodes={spec.nodes}")
    L.append(f"#SBATCH --ntasks={spec.ntasks}")
    L.append(f"#SBATCH --cpus-per-task={spec.cpus_per_task}")
    if spec.gpus > 0:
        L.append(f"#SBATCH --gres=gpu:{spec.gpus}")
    sb("--mem", spec.mem)
    sb("--time", spec.time_limit)
    out = spec.output or (f"{spec.workdir.rstrip('/')}/logs/%j.out" if spec.workdir else "%j.out")
    err = spec.error or (f"{spec.workdir.rstrip('/')}/logs/%j.err" if spec.workdir else "%j.err")
    L.append(f"#SBATCH --output={out}")
    L.append(f"#SBATCH --error={err}")
    L.append("")
    if spec.workdir:
        L.append(f"cd {shlex.quote(spec.workdir)}")
    if spec.env_setup:
        L.append(spec.env_setup)
    L.append("")
    L.append(spec.command)
    L.append("")
    return "\n".join(L)


def submit_script(ssh: SSHClient, remote_path: str, content: str) -> ExecResult:
    """写脚本到远端后 sbatch 提交。返回 ExecResult，stdout 含 'Submitted batch job <id>'。"""
    # 用 here-doc 写文件，避免本地临时文件
    heredoc = f"cat > {shlex.quote(remote_path)} <<'HPCEOF'\n{content}\nHPCEOF"
    r = ssh.exec(heredoc, timeout=20)
    if not r.ok:
        return r
    return ssh.exec(f"sbatch {shlex.quote(remote_path)}", timeout=30)


def parse_submitted_job_id(stdout: str) -> Optional[str]:
    for tok in stdout.split():
        if tok.isdigit():
            return tok
    return None
