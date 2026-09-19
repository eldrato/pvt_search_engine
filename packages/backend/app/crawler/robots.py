import time
import urllib.parse
import urllib.robotparser
from typing import Dict, Optional, Tuple
import httpx

from app.core.logging import logger
from app.crawler.allowlist import extract_domain

USER_AGENT = "AegisBot/1.0 (+https://github.com/aegis-search/aegis)"


class RobotsManager:
    """
    Manages robots.txt caching and compliance rules across domains.
    """
    def __init__(self, cache_ttl_seconds: float = 3600.0):
        self.cache_ttl = cache_ttl_seconds
        # domain -> (RobotFileParser, timestamp, crawl_delay)
        self._cache: Dict[str, Tuple[urllib.robotparser.RobotFileParser, float, Optional[float]]] = {}

    async def get_parser(self, domain: str, client: Optional[httpx.AsyncClient] = None) -> Tuple[urllib.robotparser.RobotFileParser, Optional[float]]:
        domain = domain.lower()
        now = time.time()

        if domain in self._cache:
            parser, timestamp, delay = self._cache[domain]
            if now - timestamp < self.cache_ttl:
                return parser, delay

        parser = urllib.robotparser.RobotFileParser()
        robots_url = f"https://{domain}/robots.txt"
        crawl_delay = None

        own_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=5.0, follow_redirects=True)
            own_client = True

        try:
            resp = await client.get(
                robots_url,
                headers={"User-Agent": USER_AGENT}
            )
            if resp.status_code == 200:
                parser.parse(resp.text.splitlines())
                # Try to extract crawl delay for our bot or standard
                try:
                    crawl_delay = parser.crawl_delay("AegisBot") or parser.crawl_delay("*")
                except Exception:
                    crawl_delay = None
                logger.debug(f"Loaded robots.txt for {domain} (Crawl-delay: {crawl_delay})")
            elif resp.status_code in (401, 403):
                # Forbidden robots.txt -> disallow all
                parser.disallow_all = True
                logger.warning(f"robots.txt for {domain} returned {resp.status_code}, disallowing all.")
            else:
                # 404 or other: allow all
                parser.allow_all = True
        except Exception as e:
            logger.debug(f"Could not retrieve robots.txt for {domain}: {e}. Defaulting to allow.")
            parser.allow_all = True
        finally:
            if own_client:
                await client.aclose()

        self._cache[domain] = (parser, now, crawl_delay)
        return parser, crawl_delay

    async def can_fetch(self, url: str, client: Optional[httpx.AsyncClient] = None) -> bool:
        domain = extract_domain(url)
        if not domain:
            return False

        try:
            parser, _ = await self.get_parser(domain, client=client)
            # Strictly respect both bot-specific and wildcard disallow rules
            return bool(parser.can_fetch("AegisBot", url) and parser.can_fetch("*", url))
        except Exception as err:
            logger.warning(f"Error checking robots.txt permission for {url}: {err}")
            return True


robots_manager = RobotsManager()
