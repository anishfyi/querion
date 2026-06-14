"""LLM access via the Claude Code CLI.

Querion does NOT use an API key. It shells out to the locally authenticated
Claude Code CLI (`claude`) in non-interactive print mode, with every tool
disabled, so Claude acts purely as a text generator. Authentication lives in
~/.claude on the host (browser OAuth / subscription, or an enterprise setup).

Opus is the recommended model: the analyst reasons multi-step over your schema
and API docs, and the quality gap matters. The model is configurable.
"""

import json
import shutil
import subprocess

# Variadic + greedy, so this MUST be the last group of args in the command.
TOOLS_OFF = [
    "--disallowed-tools",
    "Bash", "Edit", "Write", "Read", "Glob", "Grep",
    "WebFetch", "WebSearch", "NotebookEdit", "Task",
]


class LLMError(RuntimeError):
    pass


def claude_bin(explicit: str = "") -> str:
    return explicit or shutil.which("claude") or "claude"


def _invoke(binary, extra_args, stdin: str, timeout: int) -> str:
    """Run `claude -p --output-format json <args>` with stdin; return the text.

    The turn content is passed on stdin (never as a positional), so the greedy
    variadic --disallowed-tools cannot swallow it.
    """
    cmd = [binary, "-p", "--output-format", "json"] + list(extra_args)
    try:
        proc = subprocess.run(
            cmd, input=stdin, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        raise LLMError(f"claude CLI timed out after {timeout}s") from exc
    except FileNotFoundError as exc:
        raise LLMError(
            "claude CLI not found. Install Claude Code and run `claude` once to "
            "log in, or set claude_bin in querion.yaml."
        ) from exc

    if proc.returncode != 0:
        raise LLMError(
            f"claude CLI failed (exit {proc.returncode}): {proc.stderr.strip()[:500]}"
        )

    out = proc.stdout.strip()
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return out  # some CLI versions print plain text
    if isinstance(data, dict):
        if data.get("is_error"):
            raise LLMError(f"claude returned an error: {data.get('result') or data}")
        return (data.get("result") or "").strip()
    return out


def step(system: str, transcript: str, *, model: str = "opus",
         binary: str = "", timeout: int = 200) -> str:
    """One stateless generation. The full transcript is the turn.

    --strict-mcp-config loads zero MCP servers, so no external tool can leak in
    and the model stays a clean text generator.
    """
    args = ["--model", model, "--strict-mcp-config", "--system-prompt", system] + TOOLS_OFF
    return (_invoke(claude_bin(binary), args, transcript, timeout) or "").strip()


def available(binary: str = "") -> bool:
    return shutil.which(claude_bin(binary)) is not None or bool(shutil.which("claude"))
