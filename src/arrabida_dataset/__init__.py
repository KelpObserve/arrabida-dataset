"""Companion scripts of the KelpObserve Sesimbra 2026 dataset (doi:10.5281/zenodo.23282075)."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("arrabida-dataset")
except PackageNotFoundError:
    __version__ = "0+unknown"
