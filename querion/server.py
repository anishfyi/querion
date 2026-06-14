"""FastAPI server: the Querion web app and JSON API.

Endpoints:
  GET  /                  the Alpine.js single-page UI
  GET  /api/config        safe metadata for the UI (company, model, sources)
  POST /api/ask           start a question; returns a run id
  GET  /api/ask/{id}      poll run state (steps, answer, charts, sql)
  GET  /api/health        liveness + dependency checks

Run state lives in memory; run with a single worker (the default). Charts are
returned as spec JSON and drawn client-side by Chart.js, so no image files are
produced on the web path.
"""

import os
import threading
import time
import uuid

from querion import db, knowledge as knowledge_mod, llm
from querion.config import QuerionConfig
from querion.engine import run
from querion.safety import write_request_reason
from querion.sources import build_registry

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse
except ImportError:  # pragma: no cover
    FastAPI = None

_RUNS = {}
_RUNS_LOCK = threading.Lock()
_RUN_TTL = 60 * 60
WEB_DIR = os.path.join(os.path.dirname(__file__), "web")


def create_app(config: QuerionConfig = None):
    if FastAPI is None:
        raise RuntimeError("fastapi and uvicorn are required: pip install 'querion[web]'")
    config = config or QuerionConfig.load()
    knowledge_text = knowledge_mod.build_knowledge(config)
    sources = build_registry(config)
    limiter_state = os.path.join(config.config_dir, ".querion_usage.json")
    from querion.limits import RateLimiter
    limiter = RateLimiter(config.limits.daily_per_user, limiter_state)

    app = FastAPI(title="Querion", version="0.1.0")

    def _client_key(request: "Request") -> str:
        return (request.headers.get("x-querion-user")
                or (request.client.host if request.client else "anon"))

    @app.get("/", response_class=HTMLResponse)
    def index():
        with open(os.path.join(WEB_DIR, "index.html")) as f:
            return f.read()

    @app.get("/api/config")
    def api_config():
        return {
            "company": config.company,
            "model": config.model,
            "sources": [s.name for s in config.sources],
            "has_database": bool(config.database.dsn),
            "trove": config.trove.enabled,
            "daily_limit": config.limits.daily_per_user,
        }

    @app.get("/api/health")
    def health():
        return {
            "ok": True,
            "claude_cli": llm.available(config.claude_bin),
            "database": "ok" if (config.database.dsn and not db.ping(config.database.dsn))
                        else ("error" if config.database.dsn else "not-configured"),
            "sources": [s.name for s in config.sources],
        }

    @app.post("/api/ask")
    async def ask(request: "Request"):
        body = await request.json()
        question = (body.get("question") or "").strip()
        if not question:
            return JSONResponse({"error": "ask a question"}, status_code=400)
        # Refuse obvious write requests synchronously (no run, no quota spent).
        reason = write_request_reason(question)
        if reason:
            return JSONResponse({"refused": (
                "Read-only firewall: Querion never modifies data "
                f"({reason}). Nothing was executed.")})
        allowed, remaining = limiter.try_consume(_client_key(request))
        if not allowed:
            return JSONResponse(
                {"refused": f"Daily limit reached. Resets {limiter.reset_label()}."},
                status_code=429,
            )
        run_id = uuid.uuid4().hex[:12]
        _gc()
        with _RUNS_LOCK:
            _RUNS[run_id] = {"status": "running", "question": question, "steps": [],
                             "answer": "", "charts": [], "sqls": [], "created": time.time(),
                             "remaining": remaining}
        threading.Thread(target=_worker, args=(run_id, question, config,
                         knowledge_text, sources), daemon=True).start()
        return {"id": run_id, "remaining": remaining}

    @app.get("/api/ask/{run_id}")
    def poll(run_id: str):
        with _RUNS_LOCK:
            state = _RUNS.get(run_id)
        if not state:
            return JSONResponse({"error": "unknown run"}, status_code=404)
        return state

    return app


def _worker(run_id, question, config, knowledge_text, sources):
    def on_step(info):
        with _RUNS_LOCK:
            if run_id in _RUNS:
                _RUNS[run_id]["steps"] = (_RUNS[run_id].get("steps") or []) + [info]
    out = run(config, knowledge_text, sources, question,
              render_charts=False, on_step=on_step)
    with _RUNS_LOCK:
        prev = _RUNS.get(run_id, {})
        out["created"] = prev.get("created", time.time())
        out["question"] = question
        out["remaining"] = prev.get("remaining", -1)
        if out["status"] == "refused":
            out["answer"] = out.get("refused", "")
        _RUNS[run_id] = out


def _gc():
    now = time.time()
    with _RUNS_LOCK:
        for rid in [r for r, s in _RUNS.items() if now - s.get("created", now) > _RUN_TTL]:
            _RUNS.pop(rid, None)


def serve(config: QuerionConfig = None, host="127.0.0.1", port=8000):
    import uvicorn
    uvicorn.run(create_app(config), host=host, port=port, workers=1)
