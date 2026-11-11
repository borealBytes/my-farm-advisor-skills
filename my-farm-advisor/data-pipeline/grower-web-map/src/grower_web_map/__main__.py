"""Command-line entry point for ``python -m grower_web_map``."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from grower_web_map.builder import main
else:
    from .builder import main

raise SystemExit(main())
