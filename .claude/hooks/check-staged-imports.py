#!/usr/bin/env python3
"""Pre-commit 검증: 스테이징된 파일의 상대 import가 참조하는 파일이
git에 tracked 또는 staged 상태인지 확인한다.

누락이 발견되면 exit 2 로 커밋을 차단한다.

검출 패턴:
  TS/TSX/JS: from './X' | from '../X' | import './X'
  Python:    from .X import ... | from ..pkg.mod import ...
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout


def main() -> int:
    root = run(["git", "rev-parse", "--show-toplevel"]).strip()
    if not root:
        return 0
    os.chdir(root)

    staged = [p for p in run(["git", "diff", "--cached", "--name-only",
                              "--diff-filter=ACMR"]).splitlines() if p]
    if not staged:
        return 0

    tracked = set(run(["git", "ls-files"]).splitlines())
    # 커밋 후 시점의 파일 존재 여부 = tracked ∪ staged
    all_files = tracked | set(staged)

    ts_re = re.compile(r"""(?:from|import)\s+['"](\.\.?/[^'"]+)['"]""")
    py_re = re.compile(r"""^\s*from\s+(\.+[\w.]*)\s+import""", re.MULTILINE)

    ts_exts = [".ts", ".tsx", ".js", ".jsx",
               "/index.ts", "/index.tsx", "/index.js", "/index.jsx"]
    py_exts = [".py", "/__init__.py"]

    problems: list[tuple[str, str]] = []

    for file in staged:
        path = Path(file)
        if not path.is_file():
            continue
        suffix = path.suffix
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        base = path.parent

        if suffix in (".ts", ".tsx", ".js", ".jsx"):
            for spec in ts_re.findall(text):
                joined = os.path.normpath(base / spec)
                # 이미 확장자 포함한 경우 그대로, 아니면 후보 확장자 시도
                candidates = [joined] + [joined + ext for ext in ts_exts]
                if not any(c in all_files for c in candidates):
                    problems.append((file, spec))
        elif suffix == ".py":
            for spec in py_re.findall(text):
                dots = len(spec) - len(spec.lstrip("."))
                name = spec[dots:]
                cur = base
                for _ in range(dots - 1):
                    cur = cur.parent
                path_part = name.replace(".", "/") if name else ""
                joined = os.path.normpath(cur / path_part) if path_part else str(cur)
                candidates = [joined + ext for ext in py_exts] + [joined]
                if not any(c in all_files for c in candidates):
                    problems.append((file, f"from {spec} import ..."))

    if problems:
        print("", file=sys.stderr)
        print("❌ 커밋 차단: 스테이징된 파일이 tracked/staged 되지 않은 파일을 import 합니다.",
              file=sys.stderr)
        print("", file=sys.stderr)
        for src, spec in problems:
            print(f"  - {src} → {spec}", file=sys.stderr)
        print("", file=sys.stderr)
        print("→ 해결: 누락 파일을 git add 하거나 import를 제거하세요.", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
