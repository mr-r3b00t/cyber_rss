import time

import pytest
from test_collector import RSS

from cyber_rss.refresh import fetch_feed, refresh_sources
from cyber_rss.sources import Source
from cyber_rss.storage import ArticleStore


def test_refresh_continues_when_one_feed_fails(tmp_path):
    sources = [
        Source("cert", "Good", "https://example.org/good.xml"),
        Source("news", "Broken", "https://example.org/broken.xml"),
    ]

    def fetch(url: str) -> bytes:
        if "broken" in url:
            raise RuntimeError("timeout")
        return RSS

    store = ArticleStore(tmp_path / "news.db")
    store.initialize()

    result = refresh_sources(sources, store, fetch=fetch, workers=2)

    assert result == {
        "sources": 2,
        "successful": 1,
        "failed": 1,
        "collected": 1,
        "inserted": 1,
        "updated": 0,
        "deduplicated": 0,
        "articles": 1,
    }
    assert len(store.list_articles()) == 1


def test_fetch_feed_rejects_private_destinations_before_request():
    try:
        fetch_feed("http://127.0.0.1/internal-feed")
    except ValueError as error:
        assert "privée" in str(error)
    else:
        raise AssertionError("Une destination privée doit être refusée")


def test_refresh_fusionne_les_doublons_selon_l_ordre_des_sources(tmp_path):
    sources = [
        Source("cert", "Source prioritaire", "https://example.org/slow.xml"),
        Source("news", "Source secondaire", "https://example.org/fast.xml"),
    ]

    def fetch(url: str) -> bytes:
        if "slow" in url:
            time.sleep(0.03)
            return RSS.replace(b"Critical CVE-2026-12345", b"Titre prioritaire")
        return RSS.replace(b"Critical CVE-2026-12345", b"Titre secondaire")

    store = ArticleStore(tmp_path / "news.db")
    store.initialize()

    result = refresh_sources(sources, store, fetch=fetch, workers=2)

    assert result["collected"] == 2
    assert result["inserted"] == 1
    assert result["updated"] == 0
    assert result["deduplicated"] == 1
    assert store.list_articles()[0]["source_name"] == "Source prioritaire"
    assert store.list_articles()[0]["title"].startswith("Titre prioritaire")


def test_fetch_feed_respecte_une_echeance_totale(monkeypatch):
    class Response:
        is_redirect = False
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def raise_for_status(self):
            return None

        def iter_content(self, _size):
            yield b"premier"
            yield b"second"

    instants = iter([0.0, 0.0, 1.0, 25.0])
    monkeypatch.setattr("cyber_rss.refresh.monotonic", lambda: next(instants))
    monkeypatch.setattr("cyber_rss.refresh._validate_public_url", lambda _url: None)
    monkeypatch.setattr("cyber_rss.refresh.requests.get", lambda *_args, **_kwargs: Response())

    with pytest.raises(TimeoutError, match="échéance totale"):
        fetch_feed("https://example.org/feed.xml")
