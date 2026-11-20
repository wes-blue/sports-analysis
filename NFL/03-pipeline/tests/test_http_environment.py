"""The pipeline must run on any machine: a GitHub runner, the owner's PC, a build container.

Regression tests for the first real run on GitHub (2026-11-20): the download code looked for a CA
bundle at a path that exists only in one build environment, and on the runner the lookup itself was
refused (PermissionError), so nothing could be downloaded.
"""
import re
import ssl
from pathlib import Path

import pytest

from nflpipe import http

PACKAGE = Path(http.__file__).resolve().parent


def test_no_machine_specific_absolute_paths_in_the_package():
    offenders = []
    for source in sorted(PACKAGE.glob("*.py")):
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if re.search(r"""["'](/root/|/home/|/Users/|[A-Za-z]:\\\\)""", code):
                offenders.append(f"{source.name}:{number}: {line.strip()}")
    assert not offenders, "machine-specific absolute paths in the pipeline:\n" + "\n".join(offenders)


@pytest.mark.parametrize("variable", ["REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"])
def test_an_unusable_ca_bundle_setting_is_ignored_not_fatal(monkeypatch, tmp_path, variable):
    for name in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(variable, str(tmp_path / "missing" / "ca-bundle.crt"))
    assert isinstance(http._ssl_context(), ssl.SSLContext)


def test_a_refused_lookup_does_not_stop_the_download_code(monkeypatch):
    """What the runner did: looking at the path raises PermissionError."""
    for name in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        monkeypatch.delenv(name, raising=False)

    def refused(self, *args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "is_file", refused)
    monkeypatch.setattr(Path, "exists", refused)
    assert isinstance(http._ssl_context(), ssl.SSLContext)
