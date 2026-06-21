"""Assignment 1 Web Map Skill.

Lightweight wrapper around the data-pipeline grower web-map generator.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# Allow the skill to import the pipeline script when installed side-by-side.
_pipeline_scripts = Path(__file__).resolve().parents[3] / "data-pipeline" / "src" / "scripts"
if _pipeline_scripts.exists():
    sys.path.insert(0, str(_pipeline_scripts))


class Assignment01WebMapSkill:
    """Skill for generating lightweight grower-level interactive web maps.

    Example:
        >>> skill = Assignment01WebMapSkill()
        >>> path = skill.create_map("illinois-grower")
        >>> print(path)
        .../growers/illinois-grower/derived/grower_webmap.html
    """

    def __init__(self) -> None:
        """Initialise the skill."""
        pass

    def create_map(self, grower_slug: str, output_dir: str | Path | None = None) -> Path:
        """Generate a self-contained HTML web map for the specified grower.

        Args:
            grower_slug: The grower identifier (e.g. ``illinois-grower``).
            output_dir: Optional override for the output directory.  When omitted
                the map is written to ``growers/<grower>/derived/`` under the
                configured runtime root.

        Returns:
            Path to the generated HTML file.
        """
        # Import here so the skill class can be instantiated even when the
        # pipeline script is not on PYTHONPATH.
        try:
            from admin.generate_grower_webmap import generate_grower_webmap  # type: ignore[import-untyped]
        except ImportError:
            # Fallback: import as a top-level module via sys.path manipulation
            admin_dir = _pipeline_scripts / "admin"
            sys.path.insert(0, str(admin_dir))
            from generate_grower_webmap import generate_grower_webmap  # type: ignore[import-untyped]

        resolved_out: Path | None = Path(output_dir) if output_dir else None
        return generate_grower_webmap(grower_slug, output_dir=resolved_out)
