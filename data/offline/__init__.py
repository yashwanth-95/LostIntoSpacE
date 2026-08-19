"""The offline knowledge package.

Everything the product can answer with no network. Every item states its
upstream source and the dataset version it shipped in.
"""

from .package import (
    OFFLINE_DATASET_DATE,
    OfflineItem,
    OfflinePackage,
    build_offline_package,
)

__all__ = [
    "build_offline_package",
    "OfflinePackage",
    "OfflineItem",
    "OFFLINE_DATASET_DATE",
]
