"""Run from project root: python -m scripts.sync_sources [--all]
Refreshes public recipe URL metadata, not copied recipe text. No API keys.
"""

import argparse
import asyncio
import json
from pathlib import Path
from app.services.web_recipes import SOURCES, crawl_index


async def main(all_maps):
    target = Path(__file__).parents[1] / "app/services/web_index.json"
    urls = set(json.loads(target.read_text()) if target.exists() else [])
    for host in SOURCES:
        try:
            found = await crawl_index(host, all_maps=all_maps)
            urls.update(found)
            target.write_text(json.dumps(sorted(urls), ensure_ascii=False, indent=0))
            print(host, len(found), "URLs", flush=True)
        except Exception as error:
            print(host, type(error).__name__, flush=True)
    target.write_text(json.dumps(sorted(urls), ensure_ascii=False, indent=0))
    print("Total unique URLs:", len(urls), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    asyncio.run(main(parser.parse_args().all))
