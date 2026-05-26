"""
Upload archived backups to a cloud object store — provider-agnostic.

One backend is selected at runtime via --provider; only that provider's SDK is
imported (lazily), so the others need not be installed. A clear hint is printed
if the chosen SDK is missing.

Supported providers:
  gcs    Google Cloud Storage      (pip install google-cloud-storage)
  s3     AWS S3 / S3-compatible    (pip install boto3) — R2, B2, MinIO, Spaces
         via --endpoint-url
  azure  Azure Blob Storage        (pip install azure-storage-blob)
  local  Copy to a local/mounted directory — no SDK, useful for testing/NAS

Object key layout is identical across providers:
    <dest>/YYYY/MM/DD/<archive>.7z

Credentials come from env vars bound by Jenkins withCredentials — never args:
  gcs    GOOGLE_APPLICATION_CREDENTIALS  (path to SA JSON key)
  s3     AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION,
         optional AWS_ENDPOINT_URL (or --endpoint-url) for S3-compatible stores
  azure  AZURE_STORAGE_CONNECTION_STRING
  local  none
"""
import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

from . import ui


CHUNK = 8 * 1024 * 1024  # 8 MiB


def _missing_sdk(provider: str, pip_name: str) -> NoReturn:
    print(f"[ERROR] Provider '{provider}' needs a package that isn't installed.",
          file=sys.stderr)
    print(f"[HINT]  pip install {pip_name}", file=sys.stderr)
    sys.exit(1)


def upload_gcs(dest: str, src: Path, key: str, **_) -> int:
    """dest = bucket name. Uses GOOGLE_APPLICATION_CREDENTIALS."""
    try:
        from google.cloud import storage
    except ImportError:
        _missing_sdk("gcs", "google-cloud-storage")

    client = storage.Client()
    blob = client.bucket(dest).blob(key)
    blob.chunk_size = CHUNK
    blob.upload_from_filename(str(src), timeout=600)
    return src.stat().st_size


def upload_s3(dest: str, src: Path, key: str, *,
              endpoint_url: str | None = None, region: str | None = None,
              **_) -> int:
    """
    dest = bucket name. Uses standard AWS_* env credentials.
    endpoint_url enables S3-compatible stores (Cloudflare R2, Backblaze B2,
    MinIO, DigitalOcean Spaces).
    """
    try:
        import boto3
    except ImportError:
        _missing_sdk("s3", "boto3")

    client = boto3.client("s3", endpoint_url=endpoint_url, region_name=region)
    client.upload_file(str(src), dest, key)
    return src.stat().st_size


def upload_azure(dest: str, src: Path, key: str, **_) -> int:
    """dest = container name. Uses AZURE_STORAGE_CONNECTION_STRING."""
    import os
    try:
        from azure.storage.blob import BlobServiceClient
    except ImportError:
        _missing_sdk("azure", "azure-storage-blob")

    conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not conn:
        sys.exit("AZURE_STORAGE_CONNECTION_STRING env var not set")

    service = BlobServiceClient.from_connection_string(conn)
    blob = service.get_blob_client(container=dest, blob=key)
    with open(src, "rb") as f:
        blob.upload_blob(f, overwrite=True, max_concurrency=4)
    return src.stat().st_size


def upload_local(dest: str, src: Path, key: str, **_) -> int:
    """dest = a local/mounted directory. No SDK; copies preserving the key path."""
    target = Path(dest) / key
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    return target.stat().st_size


BACKENDS = {
    "gcs": upload_gcs,
    "s3": upload_s3,
    "azure": upload_azure,
    "local": upload_local,
}


def run_upload(provider: str, dest: str, in_dir: Path, *,
               endpoint_url: str | None = None, region: str | None = None) -> list[str]:
    """Upload all *.7z in in_dir to <provider>:<dest>/YYYY/MM/DD/. Returns keys."""
    archives = sorted(in_dir.glob("*.7z"))
    if not archives:
        raise RuntimeError(f"No .7z files found in {in_dir}")

    backend = BACKENDS[provider]
    date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")

    # Upload the manifest alongside the archives so the cloud copy is
    # self-describing and verifiable.
    to_upload = list(archives)
    mani = in_dir / "manifest.json"
    if mani.exists():
        to_upload.append(mani)

    keys, total = [], 0
    for item in to_upload:
        key = f"{date_prefix}/{item.name}"
        ui.info(f"Uploading {item.name} -> {provider}:{dest}/{key}")
        size = backend(dest, item, key, endpoint_url=endpoint_url, region=region)
        total += size
        keys.append(key)
        ui.ok(f"{item.name} ({size / (1024 * 1024):.1f} MB)")

    ui.ok(f"Uploaded {len(to_upload)} file(s), {total / (1024 * 1024):.1f} MB "
          f"to {provider}:{dest}")
    return keys


def main():
    parser = argparse.ArgumentParser(description="Upload backups to a cloud object store")
    parser.add_argument("--provider", choices=sorted(BACKENDS), default="gcs",
                        help="Storage backend (default: gcs)")
    parser.add_argument("--dest", required=True,
                        help="Bucket / container / directory to upload into")
    parser.add_argument("--in", dest="in_dir", required=True, type=Path,
                        help="Directory containing .7z archives to upload")
    parser.add_argument("--endpoint-url", default=None,
                        help="S3-compatible endpoint (R2/B2/MinIO/Spaces). s3 only.")
    parser.add_argument("--region", default=None, help="Region. s3 only.")
    args = parser.parse_args()

    if not args.in_dir.exists():
        sys.exit(f"Input directory does not exist: {args.in_dir}")

    try:
        run_upload(args.provider, args.dest, args.in_dir,
                   endpoint_url=args.endpoint_url, region=args.region)
    except RuntimeError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
