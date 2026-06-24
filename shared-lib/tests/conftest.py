from __future__ import annotations

import sys
from pathlib import Path


SHARED_LIB_ROOT = Path(__file__).resolve().parents[1]
if str(SHARED_LIB_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_LIB_ROOT))
