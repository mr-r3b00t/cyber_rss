from cyber_rss import cli


def test_refresh_command_loads_readme_sources_and_reports_result(tmp_path, monkeypatch, capsys):
    readme = tmp_path / "README.md"
    readme.write_text("## cert (1)\n- [CERT](https://example.org/feed.xml)\n")
    captured = {}

    def fake_refresh(sources, store):
        captured["sources"] = list(sources)
        return {"sources": 1, "successful": 1, "failed": 0, "articles": 3}

    monkeypatch.setattr(cli, "refresh_sources", fake_refresh)

    exit_code = cli.main(
        ["refresh", "--readme", str(readme), "--database", str(tmp_path / "news.db")]
    )

    assert exit_code == 0
    assert captured["sources"][0].name == "CERT"
    assert '"articles": 3' in capsys.readouterr().out
