"""Run the repository's tracked-file whitespace checks."""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    """Return zero when working-tree and staged diffs have no whitespace errors."""
    for diff_args in (("diff", "--check"), ("diff", "--cached", "--check")):
        completed = subprocess.run(("git", *diff_args), check=False)
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
