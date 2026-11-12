from __future__ import annotations

from pathlib import Path

import duckdb

from .config import MAX_MEMORY, TMP, assert_under_root


def connect(path: Path | str, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    p = assert_under_root(Path(path))
    TMP.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(p), read_only=read_only, config={
        "memory_limit": MAX_MEMORY,
        "temp_directory": str(TMP),
        "threads": 2,
    })
    return con


def bulk_insert(con, table: str, rows: list[tuple], chunk: int = 400) -> None:
    """Multi-row parameterized INSERT (DuckDB executemany is row-at-a-time and very slow)."""
    if not rows:
        return
    width = len(rows[0])
    ph = "(" + ",".join("?" * width) + ")"
    for i in range(0, len(rows), chunk):
        part = rows[i:i + chunk]
        con.execute(f"INSERT INTO {table} VALUES " + ",".join([ph] * len(part)), [v for r in part for v in r])
