"""Fail if tracked files contain Cyrillic characters.

The project is English-only, including comments and docstrings. Mixed-language
sources are the kind of thing that creeps back one file at a time, so the check
runs in the pre-commit hook and in CI rather than living in a review checklist.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CYRILLIC = re.compile(r"[\u0400-\u04FF]")


def offending_lines(path: Path) -> list[tuple[int, str]]:
    """Return (line number, line) for every line containing Cyrillic."""
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    return [
        (number, line.strip())
        for number, line in enumerate(text.splitlines(), start=1)
        if CYRILLIC.search(line)
    ]


def main(argv: list[str]) -> int:
    """Check every path given on the command line."""
    failed = False
    for name in argv:
        path = Path(name)
        if not path.is_file():
            continue
        for number, line in offending_lines(path):
            print(f"{path}:{number}: Cyrillic found: {line[:100]}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
