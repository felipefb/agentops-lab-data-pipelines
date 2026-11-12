"""Counts characters (incl. spaces/newlines) of a text file; exit 1 if above the limit."""
import sys

text = open(sys.argv[1], encoding="utf-8").read().strip()
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
print(f"{len(text)} characters (limit {limit})")
sys.exit(0 if len(text) <= limit else 1)
