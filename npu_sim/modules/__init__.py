"""Concrete module implementations. Importing this package registers all modules.

When implementing a new module, add an import here so ModuleRegistry sees it
at startup.
"""

from npu_sim.modules import (  # noqa: F401  (side-effect: registration)
    avp,
    control,
    dagc,
    dram,
    dsb,
    dummy,
    mac,
    memory,
    probe,
    system,
    vau,
    workload,
)

__all__ = ["avp", "control", "dagc", "dram", "dsb", "dummy", "mac", "memory", "probe", "system", "vau", "workload"]
