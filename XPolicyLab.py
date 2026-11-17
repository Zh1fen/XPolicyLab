"""Compatibility package when this checkout is imported or installed as a module."""
from pathlib import Path
__path__ = [str(Path(__file__).resolve().parent)]
from XPolicyLab._robolab_compat import install
install()
