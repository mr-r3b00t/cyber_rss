from datetime import UTC, datetime

from cyber_rss.collector import Article
from cyber_rss.storage import ArticleStore


def make_article(*, fingerprint="abc", score=80, importance="critical", title="Alert"):
    now = datetime(2026, 9, 4, 8, tzinfo=UTC)
    return Article(
        fingerprint=fingerprint,
        title=title,
        url=f"https://example.org/{fingerprint}",
        summary="Summary",
        source_name="CERT Test",
        category="cert",
        published_at=now,
        collected_at=now,
        score=score,
        importance=importance,
        reasons=("identifiant CVE",),
    )


def test_upsert_deduplicates_and_updates_article(tmp_path):
    store = ArticleStore(tmp_path / "news.db")
    store.initialize()
    first = store.upsert_many([make_article(title="Initial")])
    second = store.upsert_many([make_article(title="Updated")])

    articles = store.list_articles()

    assert len(articles) == 1
    assert articles[0]["title"] == "Updated"
    assert first == {"inserted": 1, "updated": 0}
    assert second == {"inserted": 0, "updated": 1}


def test_list_articles_filters_level_and_search_and_orders_by_score(tmp_path):
    store = ArticleStore(tmp_path / "news.db")
    store.initialize()
    store.upsert_many(
        [
            make_article(fingerprint="low", score=10, importance="low", title="General news"),
            make_article(fingerprint="high", score=60, importance="high", title="Exchange CVE"),
            make_article(
                fingerprint="critical",
                score=90,
                importance="critical",
                title="Critical CVE",
            ),
        ]
    )

    articles = store.list_articles(level="critical", search="CVE")

    assert [article["fingerprint"] for article in articles] == ["critical"]


def test_sqlite_active_wal_et_busy_timeout(tmp_path):
    store = ArticleStore(tmp_path / "news.db")
    store.initialize()

    with store._connect() as db:
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert db.execute("PRAGMA busy_timeout").fetchone()[0] == 5_000


def test_list_articles_borne_recherche_et_pagine(tmp_path):
    store = ArticleStore(tmp_path / "news.db")
    store.initialize()
    store.upsert_many(
        [
            make_article(fingerprint=str(index), score=80 - index, title="A" * 200 + str(index))
            for index in range(4)
        ]
    )

    page = store.list_articles(search="A" * 500, limit=2, offset=1)

    assert [article["fingerprint"] for article in page] == ["1", "2"]


def test_rescore_all_actualise_la_recence_obsolete(tmp_path):
    store = ArticleStore(tmp_path / "news.db")
    store.initialize()
    store.upsert_many([make_article(fingerprint="recent", score=12, importance="low")])

    store.rescore_all(now=datetime(2026, 10, 4, 8, tzinfo=UTC))

    article = store.list_articles()[0]
    assert article["score"] == 4
    assert article["importance"] == "low"
    assert article["reasons"] == ["source d’alerte", "publication ancienne"]


def test_initialize_supprime_l_ancienne_table_source_status(tmp_path):
    store = ArticleStore(tmp_path / "news.db")
    store.initialize()

    with store._connect() as db:
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'source_status'"
        ).fetchall()

    assert tables == []


def test_upsert_many_accepte_un_generateur_et_garde_le_premier_doublon(tmp_path):
    store = ArticleStore(tmp_path / "news.db")
    store.initialize()
    articles = (
        article for article in [make_article(title="Premier"), make_article(title="Deuxième")]
    )

    result = store.upsert_many(articles)

    assert result == {"inserted": 1, "updated": 0}
    assert store.list_articles()[0]["title"] == "Premier"
