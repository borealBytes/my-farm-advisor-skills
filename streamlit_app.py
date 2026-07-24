import os
import sys
from pathlib import Path

_root = Path(__file__).parent
_dashboard_dir = _root / "runtime" / "data-pipeline" / "src" / "scripts" / "dashboard"

sys.path.insert(0, str(_dashboard_dir))
sys.path.insert(0, str(_root / "runtime" / "data-pipeline" / "src" / "scripts" / "lib"))

os.chdir(str(_root / "runtime" / "data-pipeline"))

import build_rowcrop_dashboard as _dash

_dash.main()

