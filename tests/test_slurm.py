"""SLURM 解析/生成纯函数单测（不连 HPC）。运行: python -m pytest tests/ -q"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import slurm


def test_parse_squeue():
    out = (
        "1433437|visien_s2|RUNNING|2:13:05|1|gpu4090n2|gpu4090\n"
        "1433440|nca pilot|PENDING|0:00|1|(Resources)|gpu4090\n"
    )
    jobs = slurm.parse_squeue(out)
    assert len(jobs) == 2
    assert jobs[0].job_id == "1433437"
    assert jobs[0].state == "RUNNING"
    assert jobs[1].name == "nca pilot"          # 含空格的名字不被切断
    assert jobs[1].reason == "(Resources)"


def test_parse_scontrol():
    out = "JobId=123 JobName=test JobState=RUNNING WorkDir=/home/user/work StdOut=/home/user/work/logs/123.out"
    d = slurm.parse_scontrol(out)
    assert d["JobId"] == "123"
    assert d["WorkDir"] == "/home/user/work"
    assert d["StdOut"].endswith("123.out")


def test_parse_gpu_dmon():
    raw = (
        "# gpu   sm   mem   enc   dec   jpg   ofa    fb  bar1 ccpm\n"
        "# Idx    %     %     %     %     %     %    MB    MB   MB\n"
        "    0   95    40     0     0     0     0  18000   12    0\n"
        "    0   88    35     0     0     0     0  18000   12    0\n"
    )
    g = slurm.parse_gpu_dmon(raw)
    assert g.sm_peak == 95
    assert g.sm_avg == 91
    assert g.fb_used_mb == 18000
    assert g.samples == 2


def test_build_sbatch():
    spec = slurm.SbatchSpec(
        job_name="exp1", account="myproj", partition="gpu",
        qos="normal", gpus=4, workdir="/home/user/work",
        command="python train.py")
    s = slurm.build_sbatch(spec)
    assert s.startswith("#!/bin/bash")
    assert "#SBATCH --job-name=exp1" in s
    assert "#SBATCH --gres=gpu:4" in s
    assert "#SBATCH --account=myproj" in s
    assert "cd /home/user/work" in s
    assert "python train.py" in s
    # 默认 output 落到 workdir/logs
    assert "/home/user/work/logs/%j.out" in s


def test_parse_submitted_job_id():
    assert slurm.parse_submitted_job_id("Submitted batch job 1433999") == "1433999"
    assert slurm.parse_submitted_job_id("error") is None
