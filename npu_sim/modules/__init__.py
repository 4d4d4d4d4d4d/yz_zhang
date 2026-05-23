"""Concrete module implementations. Importing this package registers all modules.

When implementing a new module, add an import here so ModuleRegistry sees it
at startup.
"""

from npu_sim.modules import dummy, probe  # noqa: F401  (side-effect: registration)

__all__ = ["dummy", "probe"]
