"""Regenerate entml_golden.json after intentional parser changes.

Usage (from repo root)::

    python src/tests/fixtures/entml_golden_update.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fixtures.entml_golden import write_golden_corpus


def main() -> None:
    path = write_golden_corpus()
    print(f"Updated {path}")


if __name__ == "__main__":
    main()
