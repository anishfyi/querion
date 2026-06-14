"""Querion - a strictly read-only, natural-language data analyst.

Querion connects to your Postgres database and any number of read-only HTTP
APIs, and answers business questions in plain English by reasoning like a senior
data analyst. It uses the Claude Code CLI as its brain, so it needs no API key.

Querion is platform agnostic: point it at a database and describe your APIs, and
it works. It never writes anything, anywhere.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
