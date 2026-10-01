import pytest
from app.services.web_recipes import (
    public_link,
    robots_rules,
    permitted,
    sitemap_links,
    parse_recipe,
    rank_urls,
    SearchUnavailable,
)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://klopotenko.com/x",
        "https://127.0.0.1/x",
        "https://localhost/x",
        "https://foo.internal/x",
        "https://user:pass@shuba.life/x",
        "javascript:alert(1)",
        "https://evil.example/x",
        "https://shuba.life:444/x",
    ],
)
def test_reject_bad_links(url):
    assert public_link(url) is None


def test_robots_wildcards_and_precedence():
    rules, delay = robots_rules(
        "User-agent: *\nDisallow: /search*\nDisallow: *?s=\nDisallow: /secret/\nAllow: /secret/public/\nCrawl-delay: 3\nUser-agent: Googlebot\nAllow: /\n"
    )
    assert delay == 3
    assert not permitted("https://shuba.life/search?q=soup", rules)
    assert not permitted("https://klopotenko.com/?s=soup", rules)
    assert not permitted("https://shuba.life/secret/data", rules)
    assert permitted("https://shuba.life/secret/public/recipe", rules)
    assert permitted("https://shuba.life/recipes/soup", rules)


def test_source_specific_bot_rule():
    rules, _ = robots_rules(
        "User-agent: *\nAllow: /\nUser-agent: DinnerBot\nDisallow: /\n"
    )
    assert not permitted("https://shuba.life/recipes/soup", rules)


def test_sitemap_ignores_images_and_external_urls():
    data = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://shuba.life/recipes/123-soup</loc></url><url><loc>https://evil.example/</loc></url></urlset>'
    assert sitemap_links(data) == ["https://shuba.life/recipes/123-soup"]
    with pytest.raises(SearchUnavailable):
        sitemap_links("<!DOCTYPE x><x/>")


def test_jsonld_recipe_nested_graph_and_cleaning():
    page = """<script type="application/ld+json">{"@graph":[{"@type":"WebPage"},{"@type":["Thing","Recipe"],"name":"<b>Суп</b>","recipeIngredient":["300 г курицы","1 л воды"],"totalTime":"PT30M","recipeYield":"2"}]}</script>"""
    r = parse_recipe(page, "https://shuba.life/recipes/soup")
    assert r["title"] == "Суп" and len(r["ingredients"]) == 2
    assert r["time"] == "PT30M" and r["yield"] == "2"
    assert (
        parse_recipe("<h1>Access denied</h1>", "https://shuba.life/recipes/soup")
        is None
    )


def test_cross_language_ingredient_ranking():
    urls = [
        "https://klopotenko.com/kurka-z-kartopleyu/",
        "https://klopotenko.com/salat/",
        "https://eda.rambler.ru/recepty/supy/kurinyj-sup-123",
    ]
    ranked = rank_urls(urls, "курица картошка", "ru")
    assert ranked[0].endswith("kurka-z-kartopleyu/")
    assert "https://klopotenko.com/salat/" not in ranked
