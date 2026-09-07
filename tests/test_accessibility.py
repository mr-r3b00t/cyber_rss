from pathlib import Path

ROOT = Path(__file__).parents[1]
TEMPLATE = (ROOT / "src/cyber_rss/templates/index.html").read_text(encoding="utf-8")
CSS = (ROOT / "src/cyber_rss/static/dashboard.css").read_text(encoding="utf-8")


def test_template_exposes_navigation_and_filter_state() -> None:
    assert 'class="skip-link" href="#main-content"' in TEMPLATE
    assert '<main id="main-content"' in TEMPLATE
    assert 'aria-current="page"' in TEMPLATE
    assert "selected_category == item.category" in TEMPLATE


def test_article_metadata_is_accessible_and_localized() -> None:
    assert "s’ouvre dans un nouvel onglet" in TEMPLATE
    assert 'aria-label="Priorité ' in TEMPLATE
    assert "score d’importance" in TEMPLATE
    assert "'critical': 'Critique'" in TEMPLATE
    assert "'high': 'Élevée'" in TEMPLATE
    assert "'medium': 'Moyenne'" in TEMPLATE
    assert "'low': 'Faible'" in TEMPLATE


def test_css_handles_intermediate_and_narrow_viewports() -> None:
    assert "@media (min-width:851px) and (max-width:994px)" in CSS
    assert "grid-template-columns:64px minmax(0,1fr) 120px 76px" in CSS
    assert "@media (max-width:480px)" in CSS
    assert ".filters{flex-direction:column}" in CSS
    assert ".article{grid-template-columns:1fr;" in CSS


def test_css_has_accessible_contrast_focus_and_targets() -> None:
    assert "#66717e" not in CSS.lower()
    assert "--control-line:#596575" in CSS
    assert ":focus-visible" in CSS
    assert "min-height:44px" in CSS
    assert ".skip-link" in CSS


def test_repetitive_article_accent_is_removed() -> None:
    assert ".article:before" not in CSS
