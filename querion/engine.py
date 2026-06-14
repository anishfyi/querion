"""The run loop that ties the brain to the executors.

One entry point, `run`, used by both the CLI and the web server. It applies the
write-request firewall, then drives the bounded analyst loop: think, execute the
emitted directives (independent ones together), feed results back, repeat, until
a final answer with no execute fence. Everything it touches is read-only.
"""

import re

from querion import analyst
from querion.safety import MARKER, write_request_reason

_FENCE = re.compile(r"```(run-sql|chart|source:[A-Za-z0-9_-]+)\s*.+?```",
                    re.DOTALL | re.IGNORECASE)


def run(config, knowledge_text, sources, question, *,
        render_charts=True, on_step=None):
    """Answer one question. Returns a dict:

    {status, answer, steps:[{n,kinds}], sqls:[...], charts:[spec,...], refused}

    status is 'done', 'refused', or 'error'. on_step(info) is an optional
    callback after each executed step for live progress.
    """
    result = {"status": "done", "answer": "", "steps": [], "sqls": [],
              "charts": [], "refused": ""}

    reason = write_request_reason(question)
    if reason:
        result["status"] = "refused"
        result["refused"] = (
            "Read-only firewall: Querion never modifies data "
            f"({reason}). Nothing was executed."
        )
        return result

    transcript = "User question: " + question
    max_steps = config.limits.max_steps
    per_step = config.limits.max_directives_per_step

    try:
        for n in range(1, max_steps + 1):
            reply = analyst.step(config, knowledge_text, transcript)
            if reply.lstrip().startswith(MARKER):
                note = reply.lstrip()[len(MARKER):].strip() or "data modification request"
                result["status"] = "refused"
                result["refused"] = (
                    "Read-only firewall: that asked Querion to change data "
                    f"({note}). Querion never writes. Nothing was executed."
                )
                return result

            ds = analyst.directives(reply, limit=per_step)
            if not ds:
                result["answer"] = _strip_fences(reply)
                return result

            fed = [f"[you emitted {len(ds)} directive(s)]:\n{reply}"]
            for i, (kind, body) in enumerate(ds, 1):
                out = analyst.run_directive(
                    kind, body, config=config, sources=sources,
                    charts_out=result["charts"], sqls=result["sqls"],
                    render_charts=render_charts,
                )
                fed.append(f"[result {i} - {kind}]:\n{out}")
            result["steps"].append({"n": n, "kinds": [k for k, _ in ds]})
            if on_step:
                on_step(result["steps"][-1])
            transcript += (
                "\n\n" + "\n\n".join(fed)
                + "\n\nContinue with more directives if needed, otherwise give the "
                "final answer (no execute fence)."
            )
        else:
            transcript += "\n\nStop querying now and give the final answer, no directive."
            result["answer"] = _strip_fences(analyst.step(config, knowledge_text, transcript))
    except Exception as exc:  # noqa: BLE001
        result["status"] = "error"
        result["answer"] = f"Something broke while analysing: {exc}"
    return result


def _strip_fences(text: str) -> str:
    """Remove any stray execute fences from the final answer (display ```sql kept)."""
    return _FENCE.sub("", text or "").strip() or "(no answer)"
