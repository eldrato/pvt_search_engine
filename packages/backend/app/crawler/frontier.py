import asyncio
from typing import Optional, Set, Tuple, List
from collections import deque

from app.crawler.allowlist import canonicalize_url, is_url_allowed, extract_domain


class URLFrontier:
    """
    Manages URL queue, depth tracking, and deduplication for crawling sessions.
    """
    def __init__(self, allowlist: List[str], max_depth: int = 2, max_pages: int = 50):
        self.allowlist = allowlist
        self.max_depth = max_depth
        self.max_pages = max_pages

        # Queue of (canonical_url, depth)
        self._queue: deque[Tuple[str, int]] = deque()
        # Set of seen canonical URLs (enqueued or visited)
        self._seen_urls: Set[str] = set()
        # Count of pages successfully crawled
        self._crawled_count = 0

    def add_seed(self, url: str) -> bool:
        canonical = canonicalize_url(url)
        if not is_url_allowed(canonical, self.allowlist):
            return False

        if canonical not in self._seen_urls:
            self._seen_urls.add(canonical)
            self._queue.append((canonical, 0))
            return True
        return False

    def enqueue_discovered_links(self, links: List[str], parent_depth: int) -> int:
        """
        Enqueues links discovered on a page if within max_depth and allowlist.
        Returns the number of new links enqueued.
        """
        if parent_depth + 1 > self.max_depth:
            return 0

        enqueued = 0
        for raw_url in links:
            # Check capacity
            if len(self._seen_urls) >= self.max_pages * 3:
                break

            canonical = canonicalize_url(raw_url)
            if not is_url_allowed(canonical, self.allowlist):
                continue

            if canonical not in self._seen_urls:
                self._seen_urls.add(canonical)
                self._queue.append((canonical, parent_depth + 1))
                enqueued += 1

        return enqueued

    def pop_next(self) -> Optional[Tuple[str, int]]:
        """
        Retrieves the next URL and depth to crawl.
        """
        if not self._queue:
            return None
        return self._queue.popleft()

    def record_crawled(self):
        self._crawled_count += 1

    def is_complete(self) -> bool:
        return len(self._queue) == 0 or self._crawled_count >= self.max_pages

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    @property
    def crawled_count(self) -> int:
        return self._crawled_count

    @property
    def seen_count(self) -> int:
        return len(self._seen_urls)
