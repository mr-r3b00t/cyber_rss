"""Persistance SQLite des actualités."""

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from .collector import Article
from .scoring import score_article

MAX_SEARCH_LENGTH = 200
MAX_PAGE_SIZE = 500
MAX_OFFSET = 100_000
BUSY_TIMEOUT_MS = 5_000


class ArticleStore:
    """Dépôt SQLite léger et sans service externe."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=BUSY_TIMEOUT_MS / 1_000)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        with self._connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS articles (
                    fingerprint TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    published_at TEXT,
                    collected_at TEXT NOT NULL,
                    score INTEGER NOT NULL CHECK(score BETWEEN 0 AND 100),
                    importance TEXT NOT NULL,
                    reasons TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_articles_priority
                    ON articles(score DESC, published_at DESC);
                CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
                DROP TABLE IF EXISTS source_status;
                """
            )

    def upsert_many(self, articles: Iterable[Article]) -> dict[str, int]:
        by_fingerprint: dict[str, Article] = {}
        for article in articles:
            by_fingerprint.setdefault(article.fingerprint, article)
        rows = [
            (
                article.fingerprint,
                article.title,
                article.url,
                article.summary,
                article.source_name,
                article.category,
                article.published_at.isoformat() if article.published_at else None,
                article.collected_at.isoformat(),
                article.score,
                article.importance,
                json.dumps(article.reasons, ensure_ascii=False),
            )
            for article in by_fingerprint.values()
        ]
        if not rows:
            return {"inserted": 0, "updated": 0}
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            updated = sum(
                db.execute(
                    "SELECT EXISTS(SELECT 1 FROM articles WHERE fingerprint = ?)", (row[0],)
                ).fetchone()[0]
                for row in rows
            )
            db.executemany(
                """
                INSERT INTO articles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fingerprint) DO UPDATE SET
                    title=excluded.title,
                    url=excluded.url,
                    summary=excluded.summary,
                    source_name=excluded.source_name,
                    category=excluded.category,
                    published_at=excluded.published_at,
                    collected_at=excluded.collected_at,
                    score=excluded.score,
                    importance=excluded.importance,
                    reasons=excluded.reasons
                """,
                rows,
            )
        return {"inserted": len(rows) - updated, "updated": updated}

    def rescore_all(self, *, now: datetime | None = None) -> int:
        """Recalcule les scores temporels afin qu'ils ne restent pas figés."""

        current = now or datetime.now(UTC)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                """SELECT fingerprint, title, summary, category, source_name, published_at
                   FROM articles"""
            ).fetchall()
            updates = []
            for row in rows:
                published_at = (
                    datetime.fromisoformat(row["published_at"]) if row["published_at"] else None
                )
                importance = score_article(
                    title=row["title"],
                    summary=row["summary"],
                    category=row["category"],
                    source_name=row["source_name"],
                    published_at=published_at,
                    now=current,
                )
                updates.append(
                    (
                        importance.score,
                        importance.level,
                        json.dumps(importance.reasons, ensure_ascii=False),
                        row["fingerprint"],
                    )
                )
            db.executemany(
                "UPDATE articles SET score = ?, importance = ?, reasons = ? WHERE fingerprint = ?",
                updates,
            )
        return len(updates)

    def list_articles(
        self,
        *,
        level: str | None = None,
        category: str | None = None,
        search: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict]:
        normalized_search = search[:MAX_SEARCH_LENGTH] if search else None
        query = f"%{normalized_search}%" if normalized_search else None
        bounded_limit = max(1, min(limit, MAX_PAGE_SIZE))
        bounded_offset = max(0, min(offset, MAX_OFFSET))
        with self._connect() as db:
            rows = db.execute(
                """SELECT * FROM articles
                    WHERE (? IS NULL OR importance = ?)
                      AND (? IS NULL OR category = ?)
                      AND (? IS NULL OR title LIKE ? OR summary LIKE ? OR source_name LIKE ?)
                    ORDER BY score DESC, COALESCE(published_at, collected_at) DESC
                    LIMIT ? OFFSET ?""",
                (
                    level,
                    level,
                    category,
                    category,
                    query,
                    query,
                    query,
                    query,
                    bounded_limit,
                    bounded_offset,
                ),
            ).fetchall()
        articles: list[dict] = []
        for row in rows:
            article = dict(row)
            article["reasons"] = json.loads(article["reasons"])
            articles.append(article)
        return articles

    def stats(self) -> dict:
        with self._connect() as db:
            total = db.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
            levels = {
                row["importance"]: row["count"]
                for row in db.execute(
                    "SELECT importance, COUNT(*) AS count FROM articles GROUP BY importance"
                )
            }
            categories = [
                dict(row)
                for row in db.execute(
                    """SELECT category, COUNT(*) AS count FROM articles
                       GROUP BY category ORDER BY count DESC"""
                )
            ]
        return {"total": total, "levels": levels, "categories": categories}

    def is_healthy(self) -> bool:
        """Vérifie réellement que SQLite accepte lecture et écriture."""

        try:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("CREATE TEMP TABLE healthcheck(value INTEGER)")
                db.execute("INSERT INTO healthcheck VALUES (1)")
                return db.execute("SELECT value FROM healthcheck").fetchone()[0] == 1
        except sqlite3.Error:
            return False
