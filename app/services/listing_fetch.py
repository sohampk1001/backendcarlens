import logging
import re
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def fetch_listing_text(url: Optional[str], limit: int = 12000) -> str:
    """Fetch public listing page text the user pasted. Returns empty string on failure."""
    if not url or not str(url).strip().lower().startswith(("http://", "https://")):
        return ""
    try:
        resp = requests.get(
            url.strip(),
            timeout=12,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
            },
            allow_redirects=True,
        )
        resp.raise_for_status()
        html = resp.text or ""
        html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
        html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.I)
        text = _TAG_RE.sub(" ", html)
        text = _WS_RE.sub(" ", text).strip()
        return text[:limit]
    except Exception as e:
        logger.warning(f"Could not fetch listing URL: {e}")
        return ""
