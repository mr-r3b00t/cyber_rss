"""Interface en ligne de commande du tableau de bord."""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .app import create_app
from .refresh import refresh_sources
from .sources import parse_sources
from .storage import ArticleStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cyber-rss", description="Veille cyber RSS priorisée")
    subcommands = parser.add_subparsers(dest="command", required=True)

    refresh = subcommands.add_parser("refresh", help="Collecter les flux")
    refresh.add_argument("--readme", type=Path, default=Path("README.md"))
    refresh.add_argument("--database", type=Path, default=Path("data/cyber-news.db"))

    serve = subcommands.add_parser("serve", help="Démarrer l'interface web")
    serve.add_argument("--database", type=Path, default=Path("data/cyber-news.db"))
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8080)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "refresh":
        sources = parse_sources(args.readme.read_text(encoding="utf-8"))
        store = ArticleStore(args.database)
        store.initialize()
        result = refresh_sources(sources, store)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["successful"] else 1

    app = create_app({"DATABASE": args.database})
    app.run(host=args.host, port=args.port, debug=False)
    return 0
