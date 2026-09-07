from cyber_rss.sources import Source, parse_sources


def test_parse_sources_preserves_category_name_and_url():
    markdown = """
## cert (1)
- [CERT-FR (ANSSI)](https://www.cert.ssi.gouv.fr/feed/)

## news (1)
- [CyberScoop](https://www.cyberscoop.com/feed)
"""

    assert parse_sources(markdown) == [
        Source(category="cert", name="CERT-FR (ANSSI)", url="https://www.cert.ssi.gouv.fr/feed/"),
        Source(category="news", name="CyberScoop", url="https://www.cyberscoop.com/feed"),
    ]


def test_parse_sources_ignores_non_feed_markdown():
    markdown = "# title\nText\n- not a link\n"

    assert parse_sources(markdown) == []
