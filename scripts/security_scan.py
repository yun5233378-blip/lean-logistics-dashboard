from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SECRET_PATTERNS = [
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("cloudflare token", re.compile(r"cf[a-z]{1,4}_[A-Za-z0-9_-]{20,}")),
    ("github token", re.compile(r"gh[pousr]_[A-Za-z0-9_]{30,}")),
    ("aws access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("slack token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}")),
    ("google api key", re.compile(r"AIza[0-9A-Za-z_-]{30,}")),
    (
        "postgres credentials",
        re.compile(r"postgres(?:ql)?://[^:\s/@]+:[^@\s]+@[^/\s]+/[^\s]+", re.IGNORECASE),
    ),
]


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line.strip()]


def is_binary(path: Path) -> bool:
    return b"\0" in path.read_bytes()[:4096]


def scan_file(path: Path) -> list[str]:
    rel = path.relative_to(ROOT).as_posix()
    if is_binary(path):
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    findings: list[str] = []
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            findings.append(f"{rel}: possible {label}")
    return findings


def main() -> int:
    findings: list[str] = []
    for path in tracked_files():
        findings.extend(scan_file(path))
    if findings:
        print("Security scan failed. Remove or rotate these secrets before publishing:", file=sys.stderr)
        for item in findings:
            print(f"- {item}", file=sys.stderr)
        return 1
    print("security scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
