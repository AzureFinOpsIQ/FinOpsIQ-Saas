"""Storage provider composition."""

from shared_lib.storage.factory import create_storage_provider
from shared_lib.storage.provider import StorageProvider

__all__ = ["StorageProvider", "create_storage_provider"]
