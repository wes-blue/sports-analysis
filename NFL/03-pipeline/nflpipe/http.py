"""Downloads from the nflverse GitHub releases, with retries and a local cache.

* Proxy settings come from the environment (``HTTPS_PROXY`` etc.); ``urllib`` reads them.
* CA certificates: ``SSL_CERT_FILE`` is honoured by Python itself; ``REQUESTS_CA_BUNDLE``,
  ``CURL_CA_BUNDLE`` or ``/root/.ccr/ca-bundle.crt`` (an agent sandbox) are used when present.
* A cached file is re-used when the upstream ``Last-Modified`` is unchanged, so a weekly run
  only downloads what nflverse actually re-published.
* Every downloaded file is untrusted data: it is saved, hashed and parsed as CSV, never run.
"""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE_URL = "https://github.com/nflverse/nflverse-data/releases/download/"
USER_AGENT = "nflpipe (standard-library Python)"
TIMEOUT_SECONDS = 120
ATTEMPTS = 4                     # first try plus three retries
BACKOFF_SECONDS = (2, 5, 15)
MAX_BYTES = 1_000_000_000        # refuse anything absurdly large (untrusted source)
RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}
CHUNK = 1 << 20


class NotPublished(Exception):
    """The upstream file does not exist (HTTP 404)."""


class DownloadError(Exception):
    """The file could not be downloaded after every retry."""


@dataclass
class Fetched:
    """A downloaded (or cached) upstream file and the facts recorded in sources.csv."""
    url: str
    path: Path
    last_modified: str      # ISO 8601 UTC, '' when the server sent none
    size_bytes: int
    sha256: str
    fetched_utc: str        # when the bytes were actually downloaded
    from_cache: bool


def utc_now_iso() -> str:
    """Current time as ISO 8601 UTC with a Z, second precision."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def http_date_to_iso(value: str | None) -> str:
    """Convert an HTTP date ('Wed, 18 Nov 2026 18:19:21 GMT') to '2026-11-18T18:19:21Z'."""
    if not value:
        return ""
    try:
        moment = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return ""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ssl_context() -> ssl.SSLContext:
    """Default TLS context, plus a CA bundle named by the environment when Python would miss it."""
    if os.environ.get("SSL_CERT_FILE"):
        return ssl.create_default_context()
    for candidate in (os.environ.get("REQUESTS_CA_BUNDLE"), os.environ.get("CURL_CA_BUNDLE"),
                      "/root/.ccr/ca-bundle.crt"):
        if candidate and Path(candidate).is_file():
            return ssl.create_default_context(cafile=candidate)
    return ssl.create_default_context()


_CONTEXT: ssl.SSLContext | None = None


def _open(url: str, method: str):
    """Open a URL once (redirects followed; proxy from the environment)."""
    global _CONTEXT
    if _CONTEXT is None:
        _CONTEXT = _ssl_context()
    request = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=_CONTEXT)


def _with_retries(action, url: str):
    """Run ``action()`` and retry transient failures with back-off; 404 raises NotPublished."""
    last_error: Exception | None = None
    for attempt in range(ATTEMPTS):
        try:
            return action()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise NotPublished(url) from exc
            if exc.code not in RETRY_STATUSES:
                raise DownloadError(f"HTTP {exc.code} for {url}") from exc
            last_error = exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            last_error = exc
        if attempt < ATTEMPTS - 1:
            time.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
    raise DownloadError(f"{url}: {last_error}")


def head_last_modified(url: str) -> str:
    """Upstream Last-Modified (ISO UTC) from a HEAD request; raises NotPublished on 404."""
    def action():
        with _open(url, "HEAD") as response:
            return http_date_to_iso(response.headers.get("Last-Modified"))
    return _with_retries(action, url)


def _meta_path(path: Path) -> Path:
    return path.with_name(path.name + ".meta.json")


def _read_meta(path: Path) -> dict | None:
    """Cache side-car (url, last_modified, size, sha256, fetched_utc) or None when unusable."""
    meta_file = _meta_path(path)
    if not (path.is_file() and meta_file.is_file()):
        return None
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(meta, dict) or meta.get("size_bytes") != path.stat().st_size:
        return None
    return meta


def _download(url: str, target: Path) -> tuple[str, int, str]:
    """GET url into target (via a temporary file). Returns (last_modified, size, sha256)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")

    def action():
        digest, size = hashlib.sha256(), 0
        with _open(url, "GET") as response, open(partial, "wb") as out:
            last_modified = http_date_to_iso(response.headers.get("Last-Modified"))
            expected = response.headers.get("Content-Length")
            while True:
                block = response.read(CHUNK)
                if not block:
                    break
                size += len(block)
                if size > MAX_BYTES:
                    raise DownloadError(f"{url} is larger than {MAX_BYTES} bytes; refusing it")
                digest.update(block)
                out.write(block)
        if expected and expected.isdigit() and int(expected) != size:
            raise ConnectionError(f"truncated download of {url}: {size} of {expected} bytes")
        return last_modified, size, digest.hexdigest()

    try:
        result = _with_retries(action, url)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    os.replace(partial, target)
    return result


def fetch(relative_path: str, cache_dir: Path, force: bool = False) -> Fetched:
    """Return an upstream file from the cache, downloading it when it is new or changed.

    ``relative_path`` is relative to the nflverse release base, e.g.
    ``stats_player/stats_player_week_2026.csv``. With ``force`` the cache is ignored.
    Raises NotPublished when the file does not exist upstream.
    """
    url = BASE_URL + relative_path
    path = Path(cache_dir) / relative_path
    meta = None if force else _read_meta(path)
    if meta is not None:
        upstream = head_last_modified(url)
        if upstream and upstream == meta.get("last_modified"):
            return Fetched(url, path, upstream, int(meta["size_bytes"]), meta["sha256"], meta["fetched_utc"], True)

    fetched_utc = utc_now_iso()
    last_modified, size, sha = _download(url, path)
    meta = {"url": url, "last_modified": last_modified, "size_bytes": size, "sha256": sha, "fetched_utc": fetched_utc}
    _meta_path(path).write_text(json.dumps(meta, indent=1, sort_keys=True), encoding="utf-8", newline="\n")
    return Fetched(url, path, last_modified, size, sha, fetched_utc, False)
