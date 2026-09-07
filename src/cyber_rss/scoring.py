"""Scoring explicable de l'importance des actualités cyber."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class Importance:
    """Résultat du classement avec les facteurs compréhensibles par l'analyste."""

    score: int
    level: str
    reasons: tuple[str, ...]


_RULES: tuple[tuple[re.Pattern[str], int, str], ...] = (
    (
        re.compile(r"\b(actively exploited|exploitation active|exploited in the wild)\b", re.I),
        30,
        "exploitation active",
    ),
    (re.compile(r"\b(zero[ -]?day|0[ -]?day)\b", re.I), 25, "zero-day"),
    (
        re.compile(r"\b(remote code execution|rce|wormable)\b", re.I),
        20,
        "exécution de code à distance",
    ),
    (re.compile(r"\b(ransomware|rançongiciel)\b", re.I), 20, "rançongiciel"),
    (re.compile(r"\b(critical|critique|urgent|urgence)\b", re.I), 15, "criticité annoncée"),
    (
        re.compile(r"\b(authentication bypass|contournement d.authentification)\b", re.I),
        15,
        "contournement d’authentification",
    ),
    (
        re.compile(r"\b(hospitals?|hôpitaux|hôpital|healthcare|santé|medical|médical)\b", re.I),
        15,
        "secteur santé",
    ),
)


def score_article(
    *,
    title: str,
    summary: str,
    category: str,
    source_name: str,
    published_at: datetime | None,
    now: datetime | None = None,
) -> Importance:
    """Calcule un score de 0 à 100 à partir de signaux éditoriaux explicites."""

    current = now or datetime.now(UTC)
    text = f"{title} {summary}"
    score = 0
    reasons: list[str] = []

    if category in {"cert", "vulnerability", "vendor_advisory"}:
        score += 12
        reasons.append("source d’alerte")
    if re.search(r"\bCVE-\d{4}-\d{4,}\b", text, re.I):
        score += 10
        reasons.append("identifiant CVE")

    for pattern, points, reason in _RULES:
        if pattern.search(text):
            score += points
            reasons.append(reason)

    if published_at:
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=UTC)
        age_hours = (current - published_at).total_seconds() / 3600
        if 0 <= age_hours <= 24:
            score += 12
            reasons.append("publication récente")
        elif 24 < age_hours <= 72:
            score += 7
            reasons.append("publication récente")
        elif age_hours > 24 * 14:
            score -= 8
            reasons.append("publication ancienne")

    score = max(0, min(100, score))
    if score >= 70:
        level = "critical"
    elif score >= 45:
        level = "high"
    elif score >= 25:
        level = "medium"
    else:
        level = "low"
    return Importance(score=score, level=level, reasons=tuple(reasons))
