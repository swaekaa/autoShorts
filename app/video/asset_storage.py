"""
Asset Storage
=============
Abstracts over local filesystem and Google Cloud Storage.
Falls back to local filesystem when GCS is not configured.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
from pathlib import Path
from typing import BinaryIO

from app.logging_config import get_logger

logger = get_logger(__name__)


class AssetStorage:
    """
    Uploads and downloads files to/from GCS or local storage.
    All paths are returned as storage_key strings.
    """

    def __init__(self, settings):
        self._settings = settings
        self._local_base = Path("./storage/generated")
        self._local_base.mkdir(parents=True, exist_ok=True)
        self._gcs_client = None
        self._bucket = None

        if settings.gcs_enabled:
            self._init_gcs()

    def _init_gcs(self) -> None:
        try:
            from google.cloud import storage as gcs

            client = gcs.Client(project=self._settings.gcs_project_id)
            self._bucket = client.bucket(self._settings.gcs_bucket_name)
            self._gcs_client = client
            logger.info(
                "GCS storage initialized",
                extra={"bucket": self._settings.gcs_bucket_name},
            )
        except ImportError:
            logger.warning(
                "google-cloud-storage not installed – falling back to local storage"
            )
        except Exception as exc:
            logger.error(
                "GCS initialization failed – falling back to local storage",
                extra={"error": str(exc)},
            )

    def upload(self, local_path: str | Path, storage_key: str) -> str:
        """
        Upload a file to storage. Returns the storage_key.
        If GCS is unavailable, copies to local storage dir.
        """
        local_path = Path(local_path)
        if not local_path.exists():
            raise FileNotFoundError(f"File not found for upload: {local_path}")

        if self._bucket is not None:
            blob = self._bucket.blob(storage_key)
            blob.upload_from_filename(str(local_path))
            logger.info(
                "Uploaded to GCS",
                extra={"key": storage_key, "size": local_path.stat().st_size},
            )
        else:
            dest = self._local_base / storage_key
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(local_path), str(dest))
            logger.info(
                "Stored locally",
                extra={"key": storage_key, "dest": str(dest)},
            )

        return storage_key

    def download(self, storage_key: str, local_path: str | Path) -> Path:
        """Download a file from storage to local_path. Returns the path."""
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        if self._bucket is not None:
            blob = self._bucket.blob(storage_key)
            blob.download_to_filename(str(local_path))
        else:
            src = self._local_base / storage_key
            shutil.copy2(str(src), str(local_path))

        return local_path

    def get_local_path(self, storage_key: str) -> Path:
        """
        Return the local path for a storage key.
        For GCS, downloads to a temp location.
        For local storage, returns the stored path directly.
        """
        if self._bucket is not None:
            local = Path("/tmp") / storage_key.replace("/", "_")
            return self.download(storage_key, local)
        return self._local_base / storage_key

    def exists(self, storage_key: str) -> bool:
        if self._bucket is not None:
            return self._bucket.blob(storage_key).exists()
        return (self._local_base / storage_key).exists()

    @staticmethod
    def compute_checksum(path: str | Path) -> str:
        """Compute SHA-256 checksum of a file."""
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def make_storage_key(self, job_id: int, asset_type: str, extension: str) -> str:
        """Generate a consistent storage key for a job asset."""
        return f"jobs/{job_id}/{asset_type}.{extension}"
