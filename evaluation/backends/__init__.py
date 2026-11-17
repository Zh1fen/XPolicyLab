"""Explicit backend registry; no HTTP or database dependencies."""
from . import protocol, libero, standard, hardware
BACKENDS = {"protocol": protocol, "libero": libero, "RoboDojo": standard, "RoboTwin": standard, "real": hardware}
def get_backend(name):
    try:
        return BACKENDS[name]
    except KeyError:
        raise ValueError(f"未知 benchmark: {name}") from None
