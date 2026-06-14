"""Configuration loading for Querion.

A single YAML file (default ./querion.yaml, or the path in QUERION_CONFIG)
describes the database, the read-only HTTP sources, the model, and limits.
Any ${VAR} in a string is interpolated from the environment, so secrets live in
the environment (or a .env file) and never in the config file itself.
"""

import os
import re
from dataclasses import dataclass, field

try:
    import yaml
except ImportError:  # pragma: no cover - yaml is a hard dependency, guard import
    yaml = None

_VAR_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


class ConfigError(RuntimeError):
    pass


def _interpolate(value):
    """Replace ${VAR} with the environment value, recursively across the tree."""
    if isinstance(value, str):
        return _VAR_RE.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, list):
        return [_interpolate(v) for v in value]
    if isinstance(value, dict):
        return {k: _interpolate(v) for k, v in value.items()}
    return value


@dataclass
class DatabaseConfig:
    dsn: str = ""
    statement_timeout_ms: int = 15000
    row_cap: int = 500
    schema_doc: str = ""  # optional path to a curated schema markdown file


@dataclass
class SourceConfig:
    """A read-only HTTP API the analyst may GET from.

    safe_get is a list of regular expressions matched against the start of the
    request path (sans query string). If it is non-empty, ONLY matching paths
    are allowed (default-deny) - this is how you stay read-only on APIs that
    expose state-changing operations over GET. If it is empty, any GET is
    allowed (fine for strictly RESTful APIs).
    """

    name: str
    base_url: str
    auth_header: str = ""  # "Header-Name: value", value may use ${VAR}
    safe_get: list = field(default_factory=list)
    docs: str = ""  # optional path to markdown API docs for this source
    timeout: int = 25


@dataclass
class Limits:
    daily_per_user: int = 50
    max_steps: int = 7
    max_directives_per_step: int = 4


@dataclass
class TroveConfig:
    """Optional integration with Trove (github.com/anishfyi/trove).

    Trove builds and maintains a file-based semantic layer as you work. When
    enabled, Querion folds that layer into its knowledge so it understands your
    domain vocabulary, metric definitions, and table relationships.
    """

    enabled: bool = False
    layer_path: str = ".trove/semantic.md"


@dataclass
class QuerionConfig:
    company: str = "your organization"
    model: str = "opus"  # Claude Code CLI model alias; Opus recommended
    claude_bin: str = ""  # explicit path to the `claude` binary, else autodetect
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    sources: list = field(default_factory=list)
    limits: Limits = field(default_factory=Limits)
    trove: TroveConfig = field(default_factory=TroveConfig)
    config_dir: str = "."

    @classmethod
    def load(cls, path: str = "") -> "QuerionConfig":
        if yaml is None:
            raise ConfigError("PyYAML is required: pip install pyyaml")
        path = path or os.environ.get("QUERION_CONFIG", "querion.yaml")
        if not os.path.exists(path):
            raise ConfigError(
                f"Config not found at '{path}'. Copy querion.example.yaml to "
                "querion.yaml and edit it, or set QUERION_CONFIG."
            )
        with open(path) as f:
            raw = _interpolate(yaml.safe_load(f) or {})

        db = DatabaseConfig(**(raw.get("database") or {}))
        sources = [SourceConfig(**s) for s in (raw.get("sources") or [])]
        limits = Limits(**(raw.get("limits") or {}))
        trove = TroveConfig(**(raw.get("trove") or {}))
        return cls(
            company=raw.get("company", "your organization"),
            model=raw.get("model", "opus"),
            claude_bin=raw.get("claude_bin", ""),
            database=db,
            sources=sources,
            limits=limits,
            trove=trove,
            config_dir=os.path.dirname(os.path.abspath(path)) or ".",
        )

    def source(self, name: str):
        for s in self.sources:
            if s.name == name:
                return s
        return None

    def resolve(self, path: str) -> str:
        """Resolve a config-relative path (docs, schema_doc) to an absolute one."""
        if not path:
            return ""
        return path if os.path.isabs(path) else os.path.join(self.config_dir, path)
