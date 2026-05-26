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
import tempfile
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


def test_storage(provider: str, dest: str, *, endpoint_url: str | None = None,
                 region: str | None = None) -> tuple[bool, str]:
    """
    Verify storage is reachable and WRITABLE without needing an archive.
      local : create the folder + write & delete a probe file (no residue).
      cloud : upload a tiny marker to <dest>/_connection-test/<ts>.txt — proves
              credentials + bucket/container + write permission. The marker is
              left in place (a write-only key like GCS objectCreator can't delete
              it); a bucket lifecycle rule cleans it up.
    Returns (ok, message). Never raises.
    """
    if provider not in BACKENDS:
        return False, f"unknown provider '{provider}' (choose {', '.join(sorted(BACKENDS))})"
    if not dest:
        return False, "destination not set (STORAGE_DEST)"

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if provider == "local":
        target = Path(dest)
        try:
            target.mkdir(parents=True, exist_ok=True)
            probe = target / f".conn-test-{stamp}"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            return False, f"cannot write to '{dest}': {exc}"
        return True, f"local path writable: {target.resolve()}"

    key = f"_connection-test/{stamp}.txt"
    tmp = Path(tempfile.gettempdir()) / f"conn-test-{stamp}.txt"
    tmp.write_text("connection test", encoding="utf-8")
    try:
        BACKENDS[provider](dest, tmp, key, endpoint_url=endpoint_url, region=region)
        return True, (f"write OK -> {provider}:{dest}/{key} "
                      f"(left a tiny marker; lifecycle rule will remove it)")
    except SystemExit:                       # _missing_sdk → SystemExit
        return False, (f"the {provider} SDK isn't installed "
                       f"(pip install -r requirements-{provider}.txt)")
    except Exception as exc:                 # auth / bucket / permission error
        return False, f"write failed: {exc}"
    finally:
        tmp.unlink(missing_ok=True)


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


def parse_targets(provider_csv: str, dest_csv: str) -> list[tuple[str, str]]:
    """Pair a comma list of providers with a comma list of destinations.

    'gcs,s3' + 'bucketA,bucketB' -> [('gcs','bucketA'), ('s3','bucketB')].
    A single provider with a single dest is the common case.
    """
    providers = [p.strip() for p in (provider_csv or "").split(",") if p.strip()]
    dests = [d.strip() for d in (dest_csv or "").split(",") if d.strip()]
    if not providers:
        raise RuntimeError("no storage provider set (STORAGE_PROVIDER)")
    if len(providers) != len(dests):
        raise RuntimeError(
            f"provider/destination count mismatch: {len(providers)} provider(s) "
            f"{providers} vs {len(dests)} dest(s) {dests} — they must align 1:1")
    unknown = [p for p in providers if p not in BACKENDS]
    if unknown:
        raise RuntimeError(f"unknown provider(s) {unknown}; choose from "
                           f"{', '.join(sorted(BACKENDS))}")
    return list(zip(providers, dests))


def run_upload_multi(provider_csv: str, dest_csv: str, in_dir: Path, *,
                     endpoint_url: str | None = None, region: str | None = None) -> list[str]:
    """Upload the archives to every provider:dest target."""
    targets = parse_targets(provider_csv, dest_csv)
    keys: list[str] = []
    for provider, dest in targets:
        if len(targets) > 1:
            ui.section(f"-> {provider}:{dest}")
        keys += run_upload(provider, dest, in_dir, endpoint_url=endpoint_url, region=region)
    return keys


def main():
    parser = argparse.ArgumentParser(description="Upload backups to a cloud object store")
    parser.add_argument("--provider", default="gcs",
                        help="Backend(s), comma list: gcs,s3,azure,local")
    parser.add_argument("--dest", required=True,
                        help="Destination(s), comma list aligned 1:1 with --provider")
    parser.add_argument("--in", dest="in_dir", required=True, type=Path,
                        help="Directory containing .7z archives to upload")
    parser.add_argument("--endpoint-url", default=None,
                        help="S3-compatible endpoint (R2/B2/MinIO/Spaces). s3 only.")
    parser.add_argument("--region", default=None, help="Region. s3 only.")
    args = parser.parse_args()

    if not args.in_dir.exists():
        sys.exit(f"Input directory does not exist: {args.in_dir}")

    try:
        run_upload_multi(args.provider, args.dest, args.in_dir,
                         endpoint_url=args.endpoint_url, region=args.region)
    except RuntimeError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
