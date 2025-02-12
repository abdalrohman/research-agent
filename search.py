from typing import Any, Literal

import aiohttp

from constant import MAX_SEARCH_RESULTS, SEARXNG_URL
from decorator import log
from models import SearchResult

# TODO: Add more search engine


async def search_searxng(
    query: str,
    count: int = MAX_SEARCH_RESULTS,
    *,
    language: str = "en-US",
    safesearch: int = 1,  # 0 = off, 1 = moderate, 2 = strict
    time_range: Literal["day", "month", "year"] | None = None,
    categories: list[str] | None = None,
    base_url: str = SEARXNG_URL,
) -> list[SearchResult]:
    """
    Search using SearXNG instance and return formatted results.
    """
    categories_str = "".join(categories or [])

    params: dict[str, Any] = {
        "q": query,
        "format": "json",
        "pageno": 1,
        "safesearch": safesearch,
        "language": language,
        "categories": categories_str,
        "theme": "simple",
        "image_proxy": 0,
    }

    if time_range is not None:
        params["time_range"] = time_range

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                base_url,
                params=params,
                headers={
                    "User-Agent": "Deep Search Agent",
                    "Accept": "text/html",
                    "Accept-Encoding": "gzip, deflate",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Connection": "keep-alive",
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status != 200:
                    log.error(f"[SearXNG Search] Search request failed with status {response.status}")
                    return []
                results = await response.json()
                results = results.get("results", [])

                sorted_results = sorted(results, key=lambda x: x.get("score", 0), reverse=True)[:count]

                return [
                    SearchResult(
                        url=result["url"],
                        title=result.get("title", ""),
                        snippet=result.get("content", ""),
                        relevance_score=result.get("score", 0),
                    )
                    for result in sorted_results
                ]
        except Exception as e:
            log.error(f"[SearXNG Search] Search request failed: {str(e)}")
            return []
