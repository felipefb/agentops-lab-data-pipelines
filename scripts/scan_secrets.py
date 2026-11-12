"""Pre-publication scan: secrets, credentials, private paths and model co-authorship lines. Exit 1 on findings."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"node_modules", "dist", ".git", "__pycache__", "venv", ".venv", "artifacts"}
PATTERNS = {
    "anthropic_key": r"sk-ant-[A-Za-z0-9_\-]{10,}",
    "openai_key": r"sk-[A-Za-z0-9]{32,}",
    "aws_key": r"AKIA[0-9A-Z]{16}",
    "github_token": r"gh[pousr]_[A-Za-z0-9]{30,}",
    "private_key": r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "password_assignment": r"(?i)(password|passwd|secret)\s*[:=]\s*['\"][^'\"]{6,}['\"]",
    "model_coauthor": r"(?i)co-authored-by:.*(claude|anthropic|chatgpt|openai|copilot)|generated with \[?claude",
    "email": r"[A-Za-z0-9._%+-]+@(gmail|hotmail|outlook|yahoo)\.com",
}


def files():
    try:
        out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True, check=True)
        return [ROOT / f for f in out.stdout.splitlines()]
    except Exception:  # noqa: BLE001 - not a git repo yet
        return [p for p in ROOT.rglob("*") if p.is_file() and not SKIP_DIRS & set(p.parts)]


def main() -> int:
    hits = []
    for p in files():
        if p.suffix in {".png", ".jpg", ".duckdb", ".lock"} or p.name == "scan_secrets.py" or not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for name, rx in PATTERNS.items():
            for m in re.finditer(rx, text):
                hits.append(f"{p.relative_to(ROOT)}: {name}: {m.group(0)[:12]}…")
    log = subprocess.run(["git", "log", "--format=%B"], cwd=ROOT, capture_output=True, text=True)
    if log.returncode == 0 and re.search(PATTERNS["model_coauthor"], log.stdout):
        hits.append("git history: model co-authorship trailer found")
    print("\n".join(hits) or "no findings")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
