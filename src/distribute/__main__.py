"""CLI entrypoint so ``python -m src.distribute`` works (mirrors src/digest)."""

import sys

from .main import main

if __name__ == "__main__":
    sys.exit(main())
