"""Workspace paths. Every controllable write goes under AGENTOPS_ROOT (default E:\\AgentOpsLab)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("AGENTOPS_ROOT", r"E:\AgentOpsLab"))
ARTIFACTS = Path(os.environ.get("AGENTOPS_ARTIFACTS_DIR", ROOT / "artifacts"))
RUNS = ARTIFACTS / "runs"
DATA = Path(os.environ.get("AGENTOPS_DATA_DIR", ROOT / "data"))
TMP = Path(os.environ.get("DUCKDB_TMP_DIR", ROOT / "tmp" / "duckdb"))
MAX_MEMORY = os.environ.get("AGENTOPS_MAX_MEMORY", "2GB")


def assert_under_root(p: Path) -> Path:
    """Fail closed when a write path escapes the workspace (CI may set AGENTOPS_ROOT elsewhere)."""
    rp = Path(p).resolve()
    if not str(rp).lower().startswith(str(ROOT.resolve()).lower()):
        raise PermissionError(f"write outside workspace refused: {rp}")
    return rp
