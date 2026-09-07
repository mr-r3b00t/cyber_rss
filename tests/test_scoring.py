from datetime import UTC, datetime, timedelta

from cyber_rss.scoring import score_article

NOW = datetime(2026, 9, 4, 8, tzinfo=UTC)


def test_actively_exploited_remote_code_execution_is_critical():
    result = score_article(
        title="CVE-2026-12345 actively exploited remote code execution",
        summary="Critical zero-day affecting hospitals",
        category="cert",
        source_name="CISA Cybersecurity Advisories",
        published_at=NOW - timedelta(hours=2),
        now=NOW,
    )

    assert result.level == "critical"
    assert result.score >= 70
    assert "exploitation active" in result.reasons
    assert "secteur santé" in result.reasons


def test_generic_old_blog_article_has_low_importance():
    result = score_article(
        title="Monthly security engineering retrospective",
        summary="A general discussion about defensive engineering practices.",
        category="vendor_blog",
        source_name="Example Security Blog",
        published_at=NOW - timedelta(days=20),
        now=NOW,
    )

    assert result.level == "low"
    assert result.score < 25


def test_recent_official_vulnerability_with_cve_is_at_least_medium():
    result = score_article(
        title="Advisory CVE-2026-9999",
        summary="A vulnerability update is available.",
        category="vulnerability",
        source_name="Microsoft Security Update Guide",
        published_at=NOW - timedelta(hours=4),
        now=NOW,
    )

    assert result.level in {"medium", "high", "critical"}
    assert "identifiant CVE" in result.reasons


def test_une_date_future_ne_donne_pas_de_bonus_de_recence():
    result = score_article(
        title="Information générale",
        summary="Sans signal particulier.",
        category="news",
        source_name="Test",
        published_at=NOW + timedelta(days=30),
        now=NOW,
    )

    assert result.score == 0
    assert "publication récente" not in result.reasons
