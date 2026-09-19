import time
import urllib.parse
from typing import List, Dict, Any, Optional
import httpx
from bs4 import BeautifulSoup

from app.core.logging import logger


class WebSearchService:
    """
    Privacy-preserving open web search service.
    Directly queries open web endpoints without tracking cookies, identifiers, or API keys.
    """

    SEARCH_ENDPOINT = "https://html.duckduckgo.com/html/"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 AegisSearch/1.0"

    async def search(self, query: str, limit: int = 15) -> List[Dict[str, Any]]:
        query = query.strip()
        if not query:
            return []

        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                resp = await client.post(
                    self.SEARCH_ENDPOINT,
                    data={"q": query},
                    headers=headers
                )

                if resp.status_code != 200:
                    logger.warning(f"Web search returned status {resp.status_code}")
                    return []

                return self._parse_results(resp.text, limit)

        except Exception as e:
            logger.error(f"Web search error for '{query}': {e}")
            return []

    def _parse_results(self, html: str, limit: int) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        results = []

        result_elements = soup.select(".results .result")
        if not result_elements:
            result_elements = soup.select(".result")

        for el in result_elements:
            # Title & Link
            title_tag = el.select_one(".result__title a") or el.select_one("a.result__url")
            if not title_tag:
                continue

            title = title_tag.get_text().strip()
            raw_href = title_tag.get("href", "")

            # Unquote DuckDuckGo redirect URL
            clean_url = self._extract_clean_url(raw_href)
            if not clean_url or not clean_url.startswith("http"):
                continue

            # Snippet
            snippet_tag = el.select_one(".result__snippet")
            snippet = snippet_tag.get_text().strip() if snippet_tag else ""

            # Domain
            try:
                parsed_url = urllib.parse.urlparse(clean_url)
                domain = parsed_url.netloc.replace("www.", "")
            except Exception:
                domain = "web"

            results.append({
                "title": title,
                "url": clean_url,
                "snippet": snippet,
                "domain": domain,
                "source": "open_web"
            })

            if len(results) >= limit:
                break

        return results

    def _extract_clean_url(self, raw_href: str) -> str:
        if not raw_href:
            return ""
        if "uddg=" in raw_href:
            try:
                parsed = urllib.parse.urlparse(raw_href)
                qs = urllib.parse.parse_qs(parsed.query)
                if "uddg" in qs:
                    return qs["uddg"][0]
            except Exception:
                pass
        return raw_href


web_search_service = WebSearchService()
