"""Truncation directory path.

移植自 MiMo-Code packages/opencode/src/tool/truncation-dir.ts
"""

from __future__ import annotations

import os
from pathlib import Path

TRUNCATION_DIR = os.path.join(str(Path.home()), ".craft", "tool-output")
