"""Normalisation des entrées RSS et Atom."""

import hashlib
import html
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import islice
from time import struct_time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser

from .scoring import score_article
from .sources import Source

LOGGER = logging.getLogger(__name__)
MAX_ENTRIES_PER_FEED = 100
MAX_TITLE_LENGTH = 500
MAX_SUMMARY_LENGTH = 5_000
MAX_URL_LENGTH = 2_048
_TRACKING_PARAMETERS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


@dataclass(frozen=True, slots=True)
class Article:
    """Actualité normalisée, prête à être enregistrée et affichée."""

    fingerprint: str
    title: str
    url: str
    summary: str
    source_name: str
    category: str
    published_at: datetime | None
    collected_at: datetime
    score: int
    importance: str
    reasons: tuple[str, ...]


def _to_datetime(value: struct_time | None) -> datetime | None:
    if value is None:
        return None
    return datetime(*value[:6], tzinfo=UTC)


def _plain_text(value: object, maximum: int) -> str:
    # La pré-coupe évite de parcourir des champs arbitrairement volumineux.
    raw = str(value)[: maximum * 4]
    without_tags = re.sub(r"<[^>]+>", " ", raw)
    return " ".join(html.unescape(without_tags).split())[:maximum]


def _safe_article_url(value: str) -> str | None:
    """N'accepte que les liens web absolus afin d'éviter les URI actives."""

    candidate = str(value).strip()
    if len(candidate) > MAX_URL_LENGTH:
        return None
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    host = parsed.hostname
    if host is None:
        return None
    default_port = (parsed.scheme == "http" and port == 80) or (
        parsed.scheme == "https" and port == 443
    )
    netloc = host.lower() if port is None or default_port else f"{host.lower()}:{port}"
    path = parsed.path.rstrip("/") or "/"
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_PARAMETERS
        )
    )
    return urlunsplit((parsed.scheme.lower(), netloc, path, query, ""))


def _entry_identity(entry: object, url: str) -> str:
    guid = entry.get("id", "")
    canonical_guid = _safe_article_url(guid) if guid else None
    return canonical_guid or url


def collect_source(source: Source, payload: bytes, *, now: datetime | None = None) -> list[Article]:
    """Transforme le contenu d'un flux en articles scorés."""

    collected_at = now or datetime.now(UTC)
    feed = feedparser.parse(payload)
    if feed.bozo:
        LOGGER.warning("Flux %s imparfait: %s", source.name, feed.bozo_exception)
        if not feed.entries:
            raise ValueError(f"Flux RSS invalide: {feed.bozo_exception}")
    articles: list[Article] = []
    for entry in islice(feed.entries, MAX_ENTRIES_PER_FEED):
        try:
            url = _safe_article_url(entry.get("link", ""))
            if url is None:
                continue
            title = _plain_text(entry.get("title", "Sans titre"), MAX_TITLE_LENGTH)
            summary = _plain_text(
                entry.get("summary", entry.get("description", "")), MAX_SUMMARY_LENGTH
            )
            published_at = _to_datetime(
                dict.get(entry, "published_parsed") or dict.get(entry, "updated_parsed")
            )
            if published_at and published_at > collected_at + timedelta(days=1):
                published_at = None
            identity = _entry_identity(entry, url)
            fingerprint = hashlib.sha256(identity.encode("utf-8")).hexdigest()
            importance = score_article(
                title=title,
                summary=summary,
                category=source.category,
                source_name=source.name,
                published_at=published_at,
                now=collected_at,
            )
            articles.append(
                Article(
                    fingerprint=fingerprint,
                    title=title,
                    url=url,
                    summary=summary,
                    source_name=source.name,
                    category=source.category,
                    published_at=published_at,
                    collected_at=collected_at,
                    score=importance.score,
                    importance=importance.level,
                    reasons=importance.reasons,
                )
            )
        except (AttributeError, TypeError, ValueError) as error:
            LOGGER.warning("Entrée ignorée dans %s: %s", source.name, error)
    return articles
