#!/usr/bin/env python3
"""启动仓库内的本地评测控制台。"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT.parent), str(ROOT)]
from XPolicyLab.web.server import main

if __name__ == "__main__":
    main()
