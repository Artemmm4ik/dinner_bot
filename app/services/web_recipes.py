"""Direct sitemap/HTML parsing, without API keys. Fixed source allowlist, robots,
request spacing, bounded bodies and persistent cache. Never bypass a blocked page.
"""

import asyncio
import gzip
import html
import io
import json
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, unquote
from xml.etree import ElementTree as ET
import aiohttp
from app.database.repo import repo
from app.services.planner import identify

SOURCES = {
    "klopotenko.com": (
        "https://klopotenko.com/sitemap_index.xml",
        "ranna_recipe-sitemap",
    ),
    "shuba.life": ("https://shuba.life/sitemap_index.xml", "/full-sitemap/"),
    "eda.rambler.ru": (
        "https://eda.rambler.ru/sitemap-index.xml",
        "map_RecipePagesGroup_",
    ),
}
AGENT = "DinnerBot"
MAX_BODY = 12_000_000
_robots = {}
_policy_locks = {}
_last = {}
_locks = {}


class SearchResults(list):
    def __init__(self, values, has_more=False):
        super().__init__(values)
        self.has_more = has_more


class SearchUnavailable(Exception):
    pass


def clean_text(value, limit=180):
    return re.sub(
        r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", str(value)))
    ).strip()[:limit]


def public_link(value):
    try:
        p = urlsplit(value)
        if (
            p.scheme != "https"
            or p.hostname not in SOURCES
            or p.username
            or p.password
            or p.port not in (None, 443)
        ):
            return None
        return urlunsplit((p.scheme, p.netloc, p.path, p.query, ""))
    except (ValueError, TypeError):
        return None


def robots_rules(text):
    groups = []
    agents = []
    rules = []
    delay = 2.0
    active = False
    for raw in text.splitlines() + ["User-agent: _end_"]:
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (x.strip() for x in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if active:
                groups.append((agents, rules, delay))
                agents = []
                rules = []
                delay = 2.0
                active = False
            agents.append(value.lower())
        elif agents:
            active = True
            if key in ("allow", "disallow") and value:
                rules.append((key == "allow", value))
            elif key == "crawl-delay":
                try:
                    delay = max(2.0, float(value))
                except ValueError:
                    pass
    specific = [g for g in groups if any(a != "*" and a in AGENT.lower() for a in g[0])]
    chosen = specific or [g for g in groups if "*" in g[0]]
    return [r for g in chosen for r in g[1]], max([g[2] for g in chosen] or [2.0])


def permitted(url, rules):
    p = urlsplit(url)
    target = p.path + ("?" + p.query if p.query else "")
    matches = []
    for allow, pattern in rules:
        end = pattern.endswith("$")
        raw = pattern[:-1] if end else pattern
        expression = "^" + re.escape(raw).replace(r"\*", ".*") + ("$" if end else "")
        if re.search(expression, target):
            matches.append((len(raw.replace("*", "")), allow))
    return max(matches)[1] if matches else True


async def _raw(url, delay=2.0):
    if not public_link(url):
        raise SearchUnavailable("source")
    host = urlsplit(url).hostname
    lock = _locks.setdefault(host, asyncio.Lock())
    async with lock:
        await asyncio.sleep(max(0, delay - (time.monotonic() - _last.get(host, 0))))
        _last[host] = time.monotonic()
        try:
            async with aiohttp.ClientSession(
                trust_env=True, timeout=aiohttp.ClientTimeout(total=15)
            ) as session:
                async with session.get(
                    url,
                    headers={
                        "User-Agent": "DinnerBot/1.0 (+recipe discovery; source links retained)"
                    },
                    allow_redirects=False,
                ) as r:
                    if r.status != 200:
                        raise SearchUnavailable("source")
                    chunks = []
                    size = 0
                    async for chunk in r.content.iter_chunked(65536):
                        size += len(chunk)
                        if size > MAX_BODY:
                            raise SearchUnavailable("size")
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    if body[:2] == b"\x1f\x8b":
                        with gzip.GzipFile(fileobj=io.BytesIO(body)) as zipped:
                            body = zipped.read(MAX_BODY + 1)
                        if len(body) > MAX_BODY:
                            raise SearchUnavailable("size")
                    return body.decode("utf-8-sig", errors="replace")
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            raise SearchUnavailable("network") from None


async def fetch(url):
    if not public_link(url):
        raise SearchUnavailable("source")
    host = urlsplit(url).hostname
    async with _policy_locks.setdefault(host, asyncio.Lock()):
        if host not in _robots or time.monotonic() - _robots[host][0] > 86400:
            text = await _raw(f"https://{host}/robots.txt")
            # A challenge HTML page is not a valid empty robots policy.
            if "<html" in text.lower() or "<!doctype" in text.lower():
                raise SearchUnavailable("robots")
            rules, delay = robots_rules(text)
            _robots[host] = (time.monotonic(), rules, delay)
    _, rules, delay = _robots[host]
    if not permitted(url, rules):
        raise SearchUnavailable("robots")
    if delay > 15:
        raise SearchUnavailable("robots")
    return await _raw(url, delay)


def sitemap_links(text):
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise SearchUnavailable("xml")
    try:
        root = ET.fromstring(text)
        return [
            node.text.strip()
            for node in root.findall("{*}url/{*}loc")
            + root.findall("{*}sitemap/{*}loc")
            if node.text and public_link(node.text.strip())
        ]
    except ET.ParseError:
        raise SearchUnavailable("xml") from None


def recipe_url(url):
    p = urlsplit(url)
    if p.hostname == "shuba.life":
        return "/recipes/" in p.path
    if p.hostname == "eda.rambler.ru":
        return "/recepty/" in p.path and bool(re.search(r"-\d+/?$", p.path))
    return (
        p.hostname == "klopotenko.com"
        and p.path.count("/") >= 2
        and p.path not in ("/r/", "/ru/r/", "/en/r/")
        and not p.path.startswith("/en/")
    )


async def crawl_index(host, all_maps=False):
    root, marker = SOURCES[host]
    maps = [u for u in sitemap_links(await fetch(root)) if marker in u]
    # One fresh map per source during interactive requests; the CLI can sync all.
    if not all_maps:
        maps = maps[:1]
    urls = []
    for url in maps:
        try:
            urls.extend(u for u in sitemap_links(await fetch(url)) if recipe_url(u))
        except SearchUnavailable:
            continue
    return sorted(set(urls))


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.current = None
        self.depth = 0
        self.title = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self.current = []
        if tag == "h1":
            self.in_title = True

    def handle_data(self, data):
        if self.current is not None:
            self.current.append(data)
        if self.in_title:
            self.title.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.current is not None:
            self.scripts.append("".join(self.current))
            self.current = None
        if tag == "h1":
            self.in_title = False


def parse_recipe(text, url):
    parser = PageParser()
    parser.feed(text)

    def walk(value):
        if isinstance(value, dict):
            types = value.get("@type", [])
            if types == "Recipe" or isinstance(types, list) and "Recipe" in types:
                yield value
            for item in value.values():
                yield from walk(item)
        elif isinstance(value, list):
            for item in value:
                yield from walk(item)

    for script in parser.scripts:
        try:
            data = json.loads(script)
        except (ValueError, TypeError):
            continue
        for r in walk(data):
            ingredients = r.get("recipeIngredient", [])
            if not isinstance(ingredients, list):
                continue
            title = clean_text(r.get("name") or " ".join(parser.title))
            if not title or not ingredients:
                continue
            return {
                "url": url,
                "title": title,
                "domain": urlsplit(url).hostname,
                "ingredients": [
                    clean_text(i, 220) for i in ingredients[:70] if isinstance(i, str)
                ],
                "yield": clean_text(r.get("recipeYield", ""), 80),
                "time": clean_text(r.get("totalTime", ""), 80),
            }
    # Do not pretend an article or a challenge page is a parsed recipe.
    return None


TRANSLIT = dict(
    zip(
        "абвгґдеєжзиіїйклмнопрстуфхцчшщыэюяьъ",
        [
            "a",
            "b",
            "v",
            "h",
            "g",
            "d",
            "e",
            "ye",
            "zh",
            "z",
            "y",
            "i",
            "yi",
            "y",
            "k",
            "l",
            "m",
            "n",
            "o",
            "p",
            "r",
            "s",
            "t",
            "u",
            "f",
            "kh",
            "ts",
            "ch",
            "sh",
            "shch",
            "y",
            "e",
            "yu",
            "ya",
            "",
            "",
        ],
    )
)
ALIASES = {
    "egg": ["yay", "yaic", "yaich"],
    "tomato": ["tomat", "pomidor"],
    "potato": ["kartop", "kartof"],
    "onion": ["tsybul", "luk"],
    "carrot": ["mork"],
    "chicken": ["kur", "chicken"],
    "fish": ["ryb", "rib"],
    "rice": ["rys", "ris"],
    "pasta": ["past", "makaron"],
    "cheese": ["syr", "sir"],
    "milk": ["molok"],
    "buckwheat": ["hrech", "grech"],
    "mushroom": ["hryb", "grib", "pechery", "shampin"],
    "cucumber": ["ohir", "ogur"],
    "feta": ["fet"],
    "lemon": ["lymon", "limon"],
    "cabbage": ["kapust"],
    "lentil": ["sochev", "chechev"],
    "bean": ["kvasol", "fasol"],
    "chickpea": ["nut"],
    "tuna": ["tun"],
    "corn": ["kukur"],
    "pepper": ["per"],
    "zucchini": ["kabach", "tsukin"],
    "spinach": ["shpyn", "shpin"],
    "broccoli": ["brokol", "brokkol"],
    "couscous": ["kuskus"],
    "lavash": ["lavash"],
    "yogurt": ["yohurt", "yogurt"],
    "oat": ["vivsyan", "ovsyan"],
}
STOP = {
    "рецепт",
    "рецепты",
    "рецепти",
    "приготовить",
    "приготувати",
    "ужин",
    "вечеря",
    "вечерю",
    "из",
    "изо",
    "для",
    "на",
    "за",
    "до",
    "минут",
    "хвилин",
    "блюдо",
    "страви",
    "быстро",
    "швидко",
    "и",
    "та",
    "с",
    "з",
    "без",
}


def query_groups(query):
    groups = [ALIASES[k] for k in identify(query) if k in ALIASES]
    # Also allow dish names absent from the small ingredient dictionary.
    for word in re.findall(r"[а-яіїєґёa-z]+", query.lower()):
        if word in STOP or len(word) < 3 or identify(word):
            continue
        translit = "".join(TRANSLIT.get(c, c) for c in word)
        groups.append([translit[: max(4, len(translit) - 2)]])
    return groups


def rank_urls(urls, query, lang):
    groups = query_groups(query)
    if not groups:
        return []

    def score(url):
        path = unquote(urlsplit(url).path).lower()
        hits = sum(any(v in path for v in group) for group in groups)
        preferred = (
            ("/ru/" in path or urlsplit(url).hostname == "eda.rambler.ru")
            if lang == "ru"
            else ("/ru/" not in path and urlsplit(url).hostname != "eda.rambler.ru")
        )
        return hits, int(preferred)

    return sorted(
        [u for u in urls if score(u)[0]], key=lambda u: (-score(u)[0], -score(u)[1], u)
    )


async def index_urls():
    seed = Path(__file__).with_name("web_index.json")
    base = json.loads(seed.read_text()) if seed.exists() else []
    saved = await repo._fetchall("SELECT body FROM scraper_cache WHERE key=$1", "index")
    if saved:
        base += json.loads(saved[0]["body"])
    return sorted(set(base))


async def refresh_recent():
    cached = await repo._fetchone(
        "SELECT key FROM scraper_cache WHERE key='refreshed' AND updated_at>now()-interval '1 day'"
    )
    if cached:
        return
    batches = await asyncio.gather(
        *(crawl_index(host) for host in SOURCES), return_exceptions=True
    )
    urls = await index_urls()
    for batch in batches:
        if isinstance(batch, list):
            urls += batch
    if not any(isinstance(b, list) and b for b in batches):
        return
    await cache_set("index", sorted(set(urls)))
    await cache_set("refreshed", True)


async def cache_set(key, value):
    await repo._execute(
        """INSERT INTO scraper_cache(key,body) VALUES($1,$2)
        ON CONFLICT(key) DO UPDATE SET body=$2,updated_at=now()""",
        key,
        json.dumps(value, ensure_ascii=False),
    )


async def recipe_details(url):
    if not public_link(url):
        raise SearchUnavailable("source")
    cached = await repo._fetchone(
        "SELECT body FROM scraper_cache WHERE key=$1 AND updated_at>now()-interval '7 days'",
        url,
    )
    if cached:
        return json.loads(cached["body"])
    value = parse_recipe(await fetch(url), url)
    if value:
        await cache_set(url, value)
    return value


async def search(uid, query, lang, page=0):
    # uid deliberately isn't sent to sources. No API account and no paid quota.
    if not query.strip() or page < 0 or page > 10000:
        raise SearchUnavailable("query")
    urls = await index_urls()
    if not urls:
        await refresh_recent()
        urls = await index_urls()
    ranked = rank_urls(urls, query, lang)
    candidates = ranked[page * 5 : page * 5 + 5]

    async def one(url):
        try:
            return await recipe_details(url)
        except SearchUnavailable:
            return None

    tasks = [asyncio.create_task(one(url)) for url in candidates]
    if not tasks:
        return SearchResults([])
    done, pending = await asyncio.wait(tasks, timeout=25)
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    found = [task.result() for task in tasks if task in done]
    # Existing index enables immediate searches; refresh via /refresh_sources by admin
    # avoids tying long crawls to a webhook deadline on Render Free.
    return SearchResults([r for r in found if r], (page + 1) * 5 < len(ranked))
