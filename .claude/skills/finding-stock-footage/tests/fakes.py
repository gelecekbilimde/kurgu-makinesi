"""Offline stand-ins for http_client.Http."""
import json
import os

from helpers import FIXTURES
from model import SourceError


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


class FakeHttp:
    """get_json returns the response whose key is a substring of the URL (longest key wins);
    a value that is an Exception is raised; a callable is called with the params. Records every call."""

    def __init__(self, responses=None, cache=None, fail_downloads=()):
        self.responses = responses or {}
        self.cache = cache
        self.fail_downloads = set(fail_downloads)
        self.calls = []
        self.downloads = []

    def get_json(self, slug, url, params, headers=None, secret_params=()):
        self.calls.append({"slug": slug, "url": url, "params": dict(params), "headers": dict(headers or {}),
                           "secret_params": tuple(secret_params)})
        keys = sorted((k for k in self.responses if k in url), key=len, reverse=True)
        if not keys:
            raise SourceError(slug, f"HTTP 404 ({url})")
        value = self.responses[keys[0]]
        if callable(value):
            value = value(params)
        if isinstance(value, Exception):
            raise value
        return value

    def download(self, slug, url, dest):
        self.downloads.append(url)
        if url in self.fail_downloads:
            raise SourceError(slug, "bağlantı hatası (test)")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"video")
