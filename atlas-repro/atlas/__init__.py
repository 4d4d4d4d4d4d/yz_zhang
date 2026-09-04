"""An open reproduction of World Labs' Atlas world model.

Atlas is a multimodal autoregressive diffusion transformer whose inputs are
grounded in 3D to form a *spatial context*.  This package reproduces that
design at a scale that trains on a laptop:

    from atlas import AtlasConfig, AtlasModel

    model = AtlasModel(AtlasConfig(dim=384, depth=12, n_heads=6))
"""

from .config import AtlasConfig, TrainConfig, load_config
from .cameras import Cameras, look_at, plucker_rays, unproject_depth
from .model import AtlasModel
from .spatial_context import DEPTH, IMAGE, TEXT, Element, SpatialContext
from .text import WordTokenizer

__version__ = "0.1.0"

__all__ = [
    "AtlasConfig",
    "TrainConfig",
    "load_config",
    "AtlasModel",
    "SpatialContext",
    "Element",
    "Cameras",
    "WordTokenizer",
    "IMAGE",
    "DEPTH",
    "TEXT",
    "look_at",
    "plucker_rays",
    "unproject_depth",
    "__version__",
]
