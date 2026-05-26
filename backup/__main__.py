"""Enable `python -m backup` to run the CLI/menu."""
import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
