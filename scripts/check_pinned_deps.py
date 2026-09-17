"""Fail if any `==`-pinned line in requirements.txt lacks an explanatory comment.

Forces every pinned dependency to record *why* it's pinned (a real
compatibility reason, not "# pinned") the same way the torch pin already
does, so future readers don't have to dig through git history to find out.
"""
import re
import sys
from pathlib import Path

PIN_RE = re.compile(r"^[A-Za-z0-9_.\-]+==")

REQUIREMENTS_PATH = Path(__file__).resolve().parent.parent / "requirements.txt"


def find_undocumented_pins(lines: list[str]) -> list[str]:
    undocumented = []
    for i, line in enumerate(lines):
        if not PIN_RE.match(line.strip()):
            continue
        preceding = lines[i - 1].strip() if i > 0 else ""
        if not preceding.startswith("#"):
            undocumented.append(line.strip())
    return undocumented


def main() -> int:
    lines = REQUIREMENTS_PATH.read_text().splitlines()
    undocumented = find_undocumented_pins(lines)
    if undocumented:
        print("Pinned dependencies missing an explanatory comment:", file=sys.stderr)
        for dep in undocumented:
            print(f"  - {dep}", file=sys.stderr)
        print(
            "\nAdd a comment line directly above each pin explaining why it's "
            "pinned (see the torch pin in requirements.txt for the pattern).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
