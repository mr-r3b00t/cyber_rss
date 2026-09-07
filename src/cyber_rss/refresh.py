"""Collecte concurrente et tolérante aux erreurs des flux RSS."""

import ipaddress
import logging
import socket
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from threading import Lock
from time import monotonic
from urllib.parse import urljoin, urlsplit

import requests

from .collector import Article, collect_source
from .sources import Source
from .storage import ArticleStore

LOGGER = logging.getLogger(__name__)
MAX_FEED_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 3
FEED_TOTAL_TIMEOUT = 20.0
_REFRESH_LOCK = Lock()


def _validate_public_url(url: str) -> None:
    """Refuse les destinations locales ou privées pour limiter les risques SSRF."""

    parsed = urlsplit(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ValueError("Schéma d'URL non autorisé")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    if not addresses:
        raise ValueError("Destination impossible à résoudre")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("Destination privée ou non routable refusée")


def fetch_feed(url: str) -> bytes:
    """Télécharge un flux avec délai et limite de taille."""

    headers = {"User-Agent": "CyberRSS-Dashboard/0.1 (+https://github.com/mr-r3b00t/cyber_rss)"}
    current_url = url
    deadline = monotonic() + FEED_TOTAL_TIMEOUT
    for redirect_count in range(MAX_REDIRECTS + 1):
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError("Flux interrompu après l’échéance totale")
        _validate_public_url(current_url)
        with requests.get(
            current_url,
            headers=headers,
            timeout=(min(4.0, remaining), remaining),
            stream=True,
            allow_redirects=False,
        ) as response:
            if response.is_redirect:
                if redirect_count == MAX_REDIRECTS:
                    raise ValueError("Trop de redirections")
                current_url = urljoin(current_url, response.headers["Location"])
                continue
            response.raise_for_status()
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_content(64 * 1024):
                if monotonic() >= deadline:
                    raise TimeoutError("Flux interrompu après l’échéance totale")
                size += len(chunk)
                if size > MAX_FEED_BYTES:
                    raise ValueError("Flux supérieur à 5 Mio")
                chunks.append(chunk)
            return b"".join(chunks)
    raise ValueError("Redirection non résolue")


def refresh_sources(
    sources: Iterable[Source],
    store: ArticleStore,
    *,
    fetch: Callable[[str], bytes] = fetch_feed,
    workers: int = 8,
) -> dict[str, int]:
    """Collecte toutes les sources sans interrompre le lot en cas d'échec isolé."""

    with _REFRESH_LOCK:
        source_list = list(sources)
        successful = 0
        failed = 0
        refresh_time = datetime.now(UTC)
        results: list[list[Article] | None] = [None] * len(source_list)

        def collect(source: Source) -> list[Article]:
            return collect_source(source, fetch(source.url), now=refresh_time)

        with ThreadPoolExecutor(max_workers=max(1, min(workers, 16))) as pool:
            futures = {
                pool.submit(collect, source): (index, source)
                for index, source in enumerate(source_list)
            }
            for future in as_completed(futures):
                index, source = futures[future]
                try:
                    results[index] = future.result()
                    successful += 1
                except Exception as error:  # une source invalide ne doit pas stopper la veille
                    failed += 1
                    LOGGER.warning("Échec du flux %s: %s", source.name, error)

        collected_articles = [article for result in results if result for article in result]
        unique_articles: dict[str, Article] = {}
        for article in collected_articles:
            unique_articles.setdefault(article.fingerprint, article)

        store.rescore_all(now=refresh_time)
        writes = store.upsert_many(unique_articles.values())
        changed = writes["inserted"] + writes["updated"]
        return {
            "sources": len(source_list),
            "successful": successful,
            "failed": failed,
            "collected": len(collected_articles),
            "inserted": writes["inserted"],
            "updated": writes["updated"],
            "deduplicated": len(collected_articles) - len(unique_articles),
            "articles": changed,
        }
