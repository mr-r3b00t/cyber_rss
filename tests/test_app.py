from test_storage import make_article

from cyber_rss.app import create_app
from cyber_rss.storage import ArticleStore


def test_dashboard_and_api_show_ranked_articles(tmp_path):
    database = tmp_path / "news.db"
    store = ArticleStore(database)
    store.initialize()
    store.upsert_many([make_article(title="Critical Exchange CVE")])
    app = create_app({"DATABASE": database, "TESTING": True})
    client = app.test_client()

    page = client.get("/")
    response = client.get("/api/articles?level=critical")

    assert page.status_code == 200
    assert "Veille Cyber" in page.text
    assert "Critical Exchange CVE" in page.text
    assert response.status_code == 200
    assert response.json["articles"][0]["score"] == 80


def test_health_endpoint_reports_ready_database(tmp_path):
    app = create_app({"DATABASE": tmp_path / "news.db", "TESTING": True})

    response = app.test_client().get("/health")

    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_api_articles_borne_la_recherche_et_pagine(tmp_path):
    database = tmp_path / "news.db"
    store = ArticleStore(database)
    store.initialize()
    store.upsert_many(
        [
            make_article(fingerprint=str(index), score=80 - index, title="A" * 200 + str(index))
            for index in range(4)
        ]
    )
    app = create_app({"DATABASE": database, "TESTING": True})

    response = app.test_client().get(f"/api/articles?q={'A' * 500}&limit=2&offset=1")

    assert response.status_code == 200
    assert [article["fingerprint"] for article in response.json["articles"]] == ["1", "2"]
    assert response.json["limit"] == 2
    assert response.json["offset"] == 1


def test_api_articles_refuse_une_pagination_non_numerique(tmp_path):
    app = create_app({"DATABASE": tmp_path / "news.db", "TESTING": True})

    response = app.test_client().get("/api/articles?limit=beaucoup")

    assert response.status_code == 400
    assert response.json == {"error": "Paramètres de pagination invalides"}


def test_health_endpoint_signale_une_base_indisponible(tmp_path, monkeypatch):
    app = create_app({"DATABASE": tmp_path / "news.db", "TESTING": True})
    monkeypatch.setattr(ArticleStore, "is_healthy", lambda _store: False)

    response = app.test_client().get("/health")

    assert response.status_code == 503
    assert response.json == {"status": "degraded"}
