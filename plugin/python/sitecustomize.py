"""Make optional vendored packages (e.g. fastembed) importable.

Only active when the plugin ships a `vendor/` directory, so the base install
stays small.
"""

import sys
from pathlib import Path

_vendor = Path(__file__).resolve().parent / "vendor"
if _vendor.is_dir():
    sys.path.append(str(_vendor))
