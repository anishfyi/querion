"""Generic read-only HTTP connectors.

Each configured source is an HTTP API the analyst may GET from. The integrator
supplies a base URL, an auth header, and (recommended) a safe-read allowlist.
This module enforces: GET only, allowlist (default-deny when configured), and a
payload cap. A POST/PUT/PATCH/DELETE never leaves this process.

This is the lesson learned the hard way: a GET is not automatically read-only.
Some real APIs expose state-changing operations over GET, so an allowlist of
known read paths is the only safe default for them.
"""

import json

import requests

from querion.config import SourceConfig
from querion.safety import HttpReadError, compile_allowlist, path_allowed, read_verb

MAX_CHARS = 6000  # cap the payload fed back into the analyst


class Source:
    def __init__(self, cfg: SourceConfig):
        self.cfg = cfg
        self.allowlist_re = compile_allowlist(cfg.safe_get)
        self._header_name, self._header_value = self._parse_auth(cfg.auth_header)

    @staticmethod
    def _parse_auth(auth_header: str):
        if not auth_header or ":" not in auth_header:
            return "", ""
        name, _, value = auth_header.partition(":")
        return name.strip(), value.strip()

    def get(self, directive: str) -> str:
        path = read_verb(directive)
        if not path_allowed(path, self.allowlist_re):
            head = path.split("?", 1)[0].strip()
            raise HttpReadError(
                f"Refused: '{head}' is not on the '{self.cfg.name}' safe-read "
                "allowlist. Configure source.safe_get with the read endpoints you "
                "want Querion to use (some APIs expose writes over GET)."
            )
        url = self.cfg.base_url.rstrip("/") + ("" if path.startswith("/") else "/") + path
        headers = {}
        if self._header_name:
            headers[self._header_name] = self._header_value
        resp = requests.get(url, headers=headers, timeout=self.cfg.timeout)
        return _format(resp)


def _format(resp) -> str:
    try:
        body = json.dumps(resp.json(), default=str)
    except Exception:  # noqa: BLE001
        body = resp.text or ""
    return f"HTTP {resp.status_code}\n{body[:MAX_CHARS]}"


def build_registry(config) -> dict:
    """name -> Source for every configured HTTP source."""
    return {s.name: Source(s) for s in config.sources}
