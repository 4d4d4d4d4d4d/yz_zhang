"""Datasets for the Atlas reproduction."""

from .synthetic import Scene, SyntheticWorlds, orbit_cameras, random_scene, render

__all__ = ["SyntheticWorlds", "Scene", "render", "random_scene", "orbit_cameras", "PosedFrames", "build_dataset"]


def __getattr__(name: str):
    # PosedFrames pulls in Pillow/NumPy; keep the import lazy.
    if name == "PosedFrames":
        from .posed import PosedFrames

        return PosedFrames
    raise AttributeError(name)


def build_dataset(kind: str, **kwargs):
    """Instantiate a dataset by name."""
    if kind == "synthetic":
        return SyntheticWorlds(**kwargs)
    if kind == "posed":
        from .posed import PosedFrames

        kwargs.pop("length", None)
        kwargs.pop("seed", None)
        return PosedFrames(**kwargs)
    raise ValueError(f"unknown dataset {kind!r}")
