"""
tasks/utils.py — Shared utilities for Celery task modules.
"""
from pathlib import Path


def get_run_dir(run_id: str, tool_name: str) -> Path:
    """
    Return (and create) a per-tool output directory inside the run workspace.
    Centralised here to avoid duplication across recon_tasks, vuln_tasks, etc.
    """
    run_dir = Path(f"runs/{run_id}/tools/{tool_name}")
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir
