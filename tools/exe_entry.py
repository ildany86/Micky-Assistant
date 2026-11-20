"""Punto de entrada del ejecutable de Miky."""

from __future__ import annotations

import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from miky.__main__ import main

    raise SystemExit(main(sys.argv[1:]))
