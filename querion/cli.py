"""Querion command line.

  querion check                 validate config, test DB + claude CLI
  querion introspect [-o FILE]  write a schema markdown from the live database
  querion ask "question"        answer one question in the terminal
  querion serve [--host --port] run the web app + API

Config is read from ./querion.yaml or $QUERION_CONFIG. Secrets come from the
environment (a .env file is auto-loaded if python-dotenv is installed).
"""

import argparse
import sys

from querion import __version__


def _load_dotenv():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def _config(args):
    from querion.config import QuerionConfig
    return QuerionConfig.load(args.config)


def cmd_check(args):
    from querion import db, llm
    cfg = _config(args)
    print(f"company         : {cfg.company}")
    print(f"model           : {cfg.model}")
    print(f"claude CLI      : {'found' if llm.available(cfg.claude_bin) else 'NOT FOUND'}")
    if cfg.database.dsn:
        err = db.ping(cfg.database.dsn)
        print(f"database        : {'ok (read-only)' if not err else 'ERROR ' + err}")
    else:
        print("database        : not configured")
    print(f"sources         : {', '.join(s.name for s in cfg.sources) or 'none'}")
    print(f"trove semantic  : {'enabled' if cfg.trove.enabled else 'disabled'}")
    print(f"daily per user  : {cfg.limits.daily_per_user}")
    return 0


def cmd_introspect(args):
    from querion.knowledge import introspect_schema
    cfg = _config(args)
    if not cfg.database.dsn:
        print("no database.dsn configured", file=sys.stderr)
        return 1
    md = "# Database schema\n\n" + introspect_schema(
        cfg.database.dsn, statement_timeout_ms=cfg.database.statement_timeout_ms)
    if args.output:
        with open(args.output, "w") as f:
            f.write(md + "\n")
        print(f"wrote {args.output}")
    else:
        print(md)
    return 0


def cmd_ask(args):
    from querion.engine import run
    from querion.knowledge import build_knowledge
    from querion.sources import build_registry
    cfg = _config(args)
    knowledge = build_knowledge(cfg)
    sources = build_registry(cfg)
    question = " ".join(args.question)
    print(f"Querion is thinking ({cfg.model})...\n")
    res = run(cfg, knowledge, sources, question, render_charts=True)
    if res["status"] == "refused":
        print(res["refused"])
        return 0
    for s in res["steps"]:
        print(f"  step {s['n']}: {', '.join(s['kinds'])}")
    print("\n" + res["answer"])
    if res["charts"]:
        print(f"\n[{len(res['charts'])} chart(s) generated]")
    return 0


def cmd_serve(args):
    from querion.server import serve
    serve(_config(args), host=args.host, port=args.port)
    return 0


def main(argv=None):
    _load_dotenv()
    p = argparse.ArgumentParser(prog="querion", description="Read-only natural-language data analyst.")
    p.add_argument("--version", action="version", version=f"querion {__version__}")
    p.add_argument("-c", "--config", default="", help="path to querion.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="validate config and dependencies").set_defaults(fn=cmd_check)

    pi = sub.add_parser("introspect", help="write a schema markdown from the database")
    pi.add_argument("-o", "--output", default="", help="output file (default stdout)")
    pi.set_defaults(fn=cmd_introspect)

    pa = sub.add_parser("ask", help="answer one question")
    pa.add_argument("question", nargs="+", help="the question, in plain English")
    pa.set_defaults(fn=cmd_ask)

    ps = sub.add_parser("serve", help="run the web app + API")
    ps.add_argument("--host", default="127.0.0.1")
    ps.add_argument("--port", type=int, default=8000)
    ps.set_defaults(fn=cmd_serve)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
