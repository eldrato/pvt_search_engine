import fnmatch
import re
import urllib.parse
from typing import List, Optional, Set


def normalize_domain(domain: str) -> str:
    """
    Normalizes domain string for consistent matching.
    Lowercases, removes leading http/https if present, and removes ports.
    """
    domain = domain.strip().lower()
    if domain.startswith("http://") or domain.startswith("https://"):
        parsed = urllib.parse.urlparse(domain)
        domain = parsed.netloc

    # Remove port if present
    if ":" in domain:
        domain = domain.split(":")[0]

    return domain


def extract_domain(url: str) -> Optional[str]:
    """
    Extracts the normalized domain from a URL.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        if not parsed.netloc:
            return None
        domain = parsed.netloc.lower()
        if ":" in domain:
            domain = domain.split(":")[0]
        return domain
    except Exception:
        return None


def canonicalize_url(url: str) -> str:
    """
    Canonicalizes a URL by:
    - Lowercasing scheme and netloc
    - Removing URL fragment (#anchor)
    - Normalizing path (resolving .. and .)
    - Sorting query parameters
    - Removing common tracking parameters (utm_*, ref, etc.)
    """
    parsed = urllib.parse.urlparse(url.strip())
    scheme = parsed.scheme.lower() if parsed.scheme else "https"
    netloc = parsed.netloc.lower()

    # Normalize default ports
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    path = parsed.path or "/"
    # Normalize path dots and redundant slashes
    import posixpath
    path = posixpath.normpath(path)
    if parsed.path.endswith("/") and not path.endswith("/"):
        path += "/"
    path = re.sub(r"/+", "/", path)

    # Clean and sort query parameters
    filtered_qs = []
    if parsed.query:
        query_dict = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        # Filter tracking params
        tracking_prefixes = ("utm_", "fbclid", "gclid", "ref_", "ref")
        for k, v in sorted(query_dict):
            if not any(k.lower().startswith(p) for p in tracking_prefixes):
                filtered_qs.append((k, v))

    query_str = urllib.parse.urlencode(filtered_qs) if filtered_qs else ""

    return urllib.parse.urlunparse((scheme, netloc, path, "", query_str, ""))


def is_domain_allowed(domain: str, allowlist: List[str]) -> bool:
    """
    Checks if a given domain matches any pattern in the allowlist.
    Supports:
    - Exact match: "docs.python.org" == "docs.python.org"
    - Parent domain match: "python.org" allows "python.org", "www.python.org", "docs.python.org"
    - Wildcards: "*.github.io" allows "any.github.io"
    """
    clean_target = normalize_domain(domain)

    for pattern in allowlist:
        clean_pat = normalize_domain(pattern)
        if not clean_pat:
            continue

        # Exact match
        if clean_target == clean_pat:
            return True

        # Wildcard pattern match (e.g. *.example.com)
        if "*" in clean_pat:
            if fnmatch.fnmatch(clean_target, clean_pat):
                return True

        # Subdomain match: target "sub.domain.com" matches allowlist "domain.com"
        if clean_target.endswith("." + clean_pat):
            return True

        # www variation match
        if clean_target == f"www.{clean_pat}" or clean_pat == f"www.{clean_target}":
            return True

    return False


def is_url_allowed(url: str, allowlist: List[str]) -> bool:
    """
    Determines if a URL is strictly within the allowed crawling boundary.
    """
    domain = extract_domain(url)
    if not domain:
        return False
    return is_domain_allowed(domain, allowlist)
