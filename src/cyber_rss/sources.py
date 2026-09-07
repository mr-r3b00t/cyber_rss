"""Lecture des sources RSS documentées dans le README."""

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Source:
    """Une source RSS et sa catégorie éditoriale."""

    category: str
    name: str
    url: str


_HEADING = re.compile(r"^##\s+([^\s(]+)")
_FEED = re.compile(r"^-\s+\[([^]]+)]\((https?://[^)]+)\)\s*$")


def parse_sources(markdown: str) -> list[Source]:
    """Extrait les flux RSS regroupés sous les titres Markdown de niveau 2."""

    category: str | None = None
    sources: list[Source] = []
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        heading = _HEADING.match(line)
        if heading:
            category = heading.group(1)
            continue
        feed = _FEED.match(line)
        if category and feed:
            sources.append(Source(category=category, name=feed.group(1), url=feed.group(2)))
    return sources
