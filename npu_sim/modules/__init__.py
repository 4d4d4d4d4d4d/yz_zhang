"""Concrete module implementations. Importing this package registers all modules.

When implementing a new module, add an import here so ModuleRegistry sees it
at startup.
"""

from npu_sim.modules import (  # noqa: F401  (side-effect: registration)
    avp,
    dagc,
    dsb,
    dummy,
    mac,
    probe,
    vau,
)

__all__ = ["avp", "dagc", "dsb", "dummy", "mac", "probe", "vau"]
