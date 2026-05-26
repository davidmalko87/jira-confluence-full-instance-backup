#!/usr/bin/env python3
"""Convenience shim so you can run the tool locally with `python main.py`.

The real entrypoint lives in the package at `backup/cli.py` (also exposed as the
`jira-confluence-backup` console script and via `python -m backup`).
"""
import sys

from backup.cli import main

if __name__ == "__main__":
    sys.exit(main())
