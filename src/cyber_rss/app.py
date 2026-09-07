"""Application Flask et API de consultation."""

import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from .storage import MAX_OFFSET, MAX_PAGE_SIZE, MAX_SEARCH_LENGTH, ArticleStore


def _pagination(default_limit: int = 200) -> tuple[int, int]:
    try:
        limit = int(request.args.get("limit", default_limit))
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError) as error:
        raise ValueError("Paramètres de pagination invalides") from error
    return max(1, min(limit, MAX_PAGE_SIZE)), max(0, min(offset, MAX_OFFSET))


def create_app(test_config: dict | None = None) -> Flask:
    """Construit l'application et initialise sa base SQLite."""

    app = Flask(__name__)
    default_database = Path(os.environ.get("CYBER_RSS_DB", "data/cyber-news.db"))
    app.config.from_mapping(DATABASE=default_database)
    if test_config:
        app.config.update(test_config)

    store = ArticleStore(app.config["DATABASE"])
    store.initialize()

    @app.get("/")
    def index():
        level = request.args.get("level") or None
        category = request.args.get("category") or None
        search = (request.args.get("q") or "")[:MAX_SEARCH_LENGTH] or None
        try:
            limit, offset = _pagination()
        except ValueError:
            limit, offset = 200, 0
        articles = store.list_articles(
            level=level,
            category=category,
            search=search,
            limit=limit,
            offset=offset,
        )
        stats = store.stats()
        return render_template(
            "index.html",
            articles=articles,
            stats=stats,
            selected_level=level or "",
            selected_category=category or "",
            search=search or "",
        )

    @app.get("/api/articles")
    def api_articles():
        try:
            limit, offset = _pagination()
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        articles = store.list_articles(
            level=request.args.get("level") or None,
            category=request.args.get("category") or None,
            search=(request.args.get("q") or "")[:MAX_SEARCH_LENGTH] or None,
            limit=limit,
            offset=offset,
        )
        return jsonify(
            {"articles": articles, "count": len(articles), "limit": limit, "offset": offset}
        )

    @app.get("/api/stats")
    def api_stats():
        return jsonify(store.stats())

    @app.get("/health")
    def health():
        if store.is_healthy():
            return jsonify({"status": "ok"})
        return jsonify({"status": "degraded"}), 503

    return app
