from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.client import BaseClient
from botocore.config import Config

from app.core.config import settings


class ObjectStorageNotConfigured(RuntimeError):
    pass


class ObjectStorage:
    """Optional S3-compatible backend retained for legacy media rows.

    New generation media is stored on the KSU host. Construction stays cheap and
    non-failing when S3 is absent so callers can render local media without an S3
    deployment dependency. Actual S3 operations still fail closed when the legacy
    backend is not configured.
    """

    def __init__(self) -> None:
        self.bucket = settings.s3_bucket.strip()
        self._client: BaseClient | None = None
        self._transfer: TransferConfig | None = None
        if self.bucket:
            self._client = self._build_client()
            self._transfer = TransferConfig(
                multipart_threshold=max(5 * 1024 * 1024, settings.s3_multipart_threshold_bytes),
                multipart_chunksize=max(5 * 1024 * 1024, settings.s3_multipart_chunk_bytes),
                max_concurrency=max(1, settings.s3_max_concurrency),
                use_threads=True,
            )

    @staticmethod
    def configured() -> bool:
        return bool(settings.s3_bucket.strip())

    def _require_configured(self) -> tuple[BaseClient, TransferConfig]:
        if not self.bucket or self._client is None or self._transfer is None:
            raise ObjectStorageNotConfigured("S3_BUCKET is not configured")
        return self._client, self._transfer

    @staticmethod
    def _build_client() -> BaseClient:
        kwargs: dict[str, Any] = {
            "service_name": "s3",
            "region_name": settings.s3_region or None,
            "config": Config(
                signature_version="s3v4",
                s3={"addressing_style": settings.s3_addressing_style},
            ),
        }
        if settings.s3_endpoint_url:
            kwargs["endpoint_url"] = settings.s3_endpoint_url
        if settings.s3_access_key_id:
            kwargs["aws_access_key_id"] = settings.s3_access_key_id
        if settings.s3_secret_access_key:
            kwargs["aws_secret_access_key"] = settings.s3_secret_access_key
        if settings.s3_session_token:
            kwargs["aws_session_token"] = settings.s3_session_token
        return boto3.client(**kwargs)

    async def upload_file(
        self,
        path: Path,
        *,
        key: str,
        content_type: str,
        metadata: dict[str, str],
    ) -> dict[str, Any]:
        client, transfer = self._require_configured()

        def _upload() -> dict[str, Any]:
            client.upload_file(
                str(path),
                self.bucket,
                key,
                ExtraArgs={
                    "ContentType": content_type,
                    "Metadata": metadata,
                },
                Config=transfer,
            )
            return client.head_object(Bucket=self.bucket, Key=key)

        return await asyncio.to_thread(_upload)

    async def download_file(
        self,
        path: Path,
        *,
        key: str,
        bucket: str | None = None,
    ) -> None:
        client, transfer = self._require_configured()

        def _download() -> None:
            client.download_file(
                bucket or self.bucket,
                key,
                str(path),
                Config=transfer,
            )

        await asyncio.to_thread(_download)

    def presign_get(
        self,
        *,
        key: str,
        bucket: str | None = None,
        expires_seconds: int | None = None,
        download_filename: str | None = None,
    ) -> str:
        client, _transfer = self._require_configured()
        params: dict[str, Any] = {
            "Bucket": bucket or self.bucket,
            "Key": key,
        }
        if download_filename:
            safe_name = download_filename.replace('"', "").replace("\r", "").replace("\n", "")
            params["ResponseContentDisposition"] = f'attachment; filename="{safe_name}"'
        return str(
            client.generate_presigned_url(
                "get_object",
                Params=params,
                ExpiresIn=max(60, expires_seconds or settings.media_presign_ttl_seconds),
            )
        )
