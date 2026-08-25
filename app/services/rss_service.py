"""
RSS feed ingestion service for Car Lens.
Fetches, parses, deduplicates, and queues items for Groq extraction.
"""
import re
import uuid
import logging
import warnings
import requests
from datetime import datetime
from typing import List, Dict, Optional
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)

RSS_FEED_URL = "https://rss.app/feeds/tSiBQ4IOv6Ev9AuE.xml"


def _parse_date(date_str: Optional[str]) -> Optional[str]:
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str).isoformat()
    except Exception:
        return None


def _clean_html(text: Optional[str]) -> str:
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:2000]


def fetch_rss_items() -> List[Dict]:
    """Fetch and parse RSS XML. Returns list of parsed items."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            resp = requests.get(RSS_FEED_URL, timeout=15, verify=False,
                                headers={"User-Agent": "CarLens-Bot/1.0"})
            resp.raise_for_status()
            xml = resp.text
    except Exception as e:
        logger.error(f"RSS fetch failed: {e}")
        return []

    items = []
    # Parse each <item> block
    item_blocks = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
    for block in item_blocks:
        def _get(tag):
            m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.DOTALL)
            if m:
                v = m.group(1).strip()
                v = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", v, flags=re.DOTALL)
                return v.strip()
            return None

        guid = _get("guid") or _get("link") or str(uuid.uuid4())
        title = _clean_html(_get("title"))
        description = _clean_html(_get("description"))
        url = _get("link")
        pub_date = _parse_date(_get("pubDate"))

        # Try to extract image from enclosure or media
        image_url = None
        enc = re.search(r'<enclosure[^>]*url="([^"]+)"', block)
        if enc:
            image_url = enc.group(1)
        if not image_url:
            med = re.search(r'<media:content[^>]*url="([^"]+)"', block)
            if med:
                image_url = med.group(1)

        if title or description:
            items.append({
                "guid": guid,
                "title": title,
                "description": description,
                "url": url,
                "image_url": image_url,
                "published_at": pub_date,
                "raw_xml": block[:500],
            })

    logger.info(f"RSS parsed {len(items)} items")
    return items


def sync_rss_to_db() -> Dict:
    """
    Fetch RSS, deduplicate, store new items.
    Returns sync summary.
    """
    from app.database import rss_item_exists, insert_rss_item
    items = fetch_rss_items()
    new_count = 0
    skipped = 0
    for item in items:
        if rss_item_exists(item["guid"]):
            skipped += 1
            continue
        if insert_rss_item(item):
            new_count += 1
    return {
        "total_fetched": len(items),
        "new_items": new_count,
        "skipped_duplicates": skipped,
        "synced_at": datetime.now().isoformat(),
    }


def extract_vehicle_from_text(title: str, description: str) -> Dict:
    """
    Use Groq to extract vehicle details from RSS item text.
    Returns structured dict with vehicle info or nulls — no hallucination.
    """
    from app.services.groq_service import _call_groq, _parse_json_response
    import json

    text = f"Title: {title}\n\nDescription: {description}"

    system = """You are a vehicle data extractor for the Indian used car market.
Extract ONLY what is explicitly stated. Return JSON. Use null for missing values — never guess.

Return this exact JSON structure:
{
  "brand": null,
  "model": null,
  "variant": null,
  "manufacturing_year": null,
  "registration_year": null,
  "kilometres": null,
  "asking_price": null,
  "fuel_type": null,
  "transmission": null,
  "color": null,
  "ownership": null,
  "location": null,
  "seller_type": null,
  "is_car_listing": false,
  "confidence": "low"
}

confidence: "high" if brand+model+price+km all present, "medium" if 3 present, "low" otherwise.
is_car_listing: true only if this is clearly a used car listing."""

    raw = _call_groq(system, text, temperature=0.1, max_tokens=400)
    if not raw:
        return {"is_car_listing": False, "confidence": "low"}
    parsed = _parse_json_response(raw)
    return parsed or {"is_car_listing": False, "confidence": "low"}


def process_unprocessed_items(limit: int = 10) -> Dict:
    """
    Process unprocessed RSS items through Groq extraction → listings DB.
    """
    from app.database import get_unprocessed_rss_items, mark_rss_item_processed, upsert_listing

    items = get_unprocessed_rss_items(limit=limit)
    processed = 0
    added_listings = 0

    for item in items:
        try:
            extracted = extract_vehicle_from_text(
                item.get("title", ""),
                item.get("description", "")
            )
            mark_rss_item_processed(item["id"])
            processed += 1

            if extracted.get("is_car_listing") and extracted.get("brand"):
                listing_id = f"rss_{item['id']}_{uuid.uuid4().hex[:8]}"
                listing = {
                    "id": listing_id,
                    "source": "rss_feed",
                    "source_url": item.get("url"),
                    "source_item_id": str(item.get("id")),
                    "title": item.get("title"),
                    "description": item.get("description"),
                    "asking_price": extracted.get("asking_price"),
                    "kilometres": extracted.get("kilometres"),
                    "registration_year": extracted.get("registration_year"),
                    "manufacturing_year": extracted.get("manufacturing_year"),
                    "brand": extracted.get("brand"),
                    "model": extracted.get("model"),
                    "variant": extracted.get("variant"),
                    "fuel_type": extracted.get("fuel_type"),
                    "transmission": extracted.get("transmission"),
                    "color": extracted.get("color"),
                    "ownership": extracted.get("ownership"),
                    "location": extracted.get("location"),
                    "seller_type": extracted.get("seller_type"),
                    "images": [item.get("image_url")] if item.get("image_url") else [],
                    "published_at": item.get("published_at"),
                    "listing_status": "ACTIVE_OBSERVED",
                    "extraction_status": "COMPLETED",
                    "vehicle_match_confidence": extracted.get("confidence", "low").upper()
                        if extracted.get("confidence") in ("high", "medium") else "NEEDS_VERIFICATION",
                    "groq_extracted": extracted,
                }
                if upsert_listing(listing):
                    added_listings += 1
        except Exception as e:
            logger.error(f"process_item {item.get('id')}: {e}")

    return {
        "processed": processed,
        "added_listings": added_listings,
        "processed_at": datetime.now().isoformat(),
    }
