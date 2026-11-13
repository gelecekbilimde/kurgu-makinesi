"""HTTP for the stock sources: JSON responses cached for 24 hours, atomic downloads, no secrets stored.

Named http_client (not http) so it does not shadow the standard library.
"""
import http.client
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from model import SourceError

USER_AGENT = "stock-finder/1.0"
MAX_AGE_S = 24 * 3600
TIMEOUT_S = 30
CHUNK = 1 << 20


def upgrade(url):
    """http:// -> https:// (NASA lists its files as http), except for local test servers."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme == "http" and parts.hostname not in ("127.0.0.1", "localhost"):
        return urllib.parse.urlunsplit(("https",) + tuple(parts[1:]))
    return url


def _reason(err):
    if isinstance(err, urllib.error.HTTPError):
        return "istek sınırı aşıldı (429)" if err.code == 429 else f"HTTP {err.code}"
    if isinstance(err, urllib.error.URLError):
        return f"bağlantı hatası ({err.reason})"
    if isinstance(err, http.client.HTTPException):
        return f"bağlantı kesildi ({type(err).__name__})"
    return f"bağlantı hatası ({type(err).__name__})"


class Http:
    def __init__(self, cache, clock=time.time):
        self.cache = cache
        self.clock = clock

    def _open(self, url, headers=None):
        req = urllib.request.Request(upgrade(url), headers={"User-Agent": USER_AGENT, **(headers or {})})
        return urllib.request.urlopen(req, timeout=TIMEOUT_S)

    def get_json(self, slug, url, params, headers=None, secret_params=()):
        public = sorted((k, str(v)) for k, v in params.items() if k not in secret_params)
        key = url + ("?" + urllib.parse.urlencode(public) if public else "")
        now = self.clock()
        hit = self.cache.get_response(slug, key, MAX_AGE_S, now)
        if hit is not None:
            return hit
        full = url + ("?" + urllib.parse.urlencode(params) if params else "")
        try:
            with self._open(full, headers) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as err:
            raise SourceError(slug, _reason(err)) from None
        self.cache.put_response(slug, key, data, now)
        return data

    def download(self, slug, url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_suffix(".part")
        try:
            with self._open(url) as resp, open(part, "wb") as out:
                expected = resp.headers.get("Content-Length")
                got = 0
                while chunk := resp.read(CHUNK):
                    out.write(chunk)
                    got += len(chunk)
            if expected is not None and got != int(expected):
                raise OSError(f"eksik indirme ({got}/{expected} bayt)")
            os.replace(part, dest)
        except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as err:
            part.unlink(missing_ok=True)
            raise SourceError(slug, _reason(err) if isinstance(err, (urllib.error.URLError, http.client.HTTPException))
                              else str(err)) from None
