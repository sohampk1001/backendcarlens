"""
Test script to verify multi-feed RSS functionality
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.services.rss_service import RSS_FEEDS, fetch_rss_items, sync_rss_to_db, sync_all_rss_feeds

def test_feed_config():
    """Test that RSS feeds are properly configured"""
    print("Testing RSS feed configuration...")
    print(f"Available feeds: {list(RSS_FEEDS.keys())}")
    for feed_type, url in RSS_FEEDS.items():
        print(f"  {feed_type}: {url}")
    print("✓ Feed configuration looks good\n")

def test_fetch_individual_feeds():
    """Test fetching from individual feeds"""
    print("Testing individual feed fetching...")
    for feed_type in RSS_FEEDS.keys():
        print(f"  Fetching from {feed_type}...")
        items = fetch_rss_items(feed_type)
        print(f"  ✓ {feed_type}: {len(items)} items fetched")
    print("✓ Individual feed fetching works\n")

def test_sync_individual_feeds():
    """Test syncing individual feeds to database"""
    print("Testing individual feed syncing...")
    for feed_type in RSS_FEEDS.keys():
        print(f"  Syncing {feed_type}...")
        result = sync_rss_to_db(feed_type)
        print(f"  ✓ {feed_type}: {result.get('new_items')} new items, {result.get('skipped_duplicates')} skipped")
    print("✓ Individual feed syncing works\n")

def test_sync_all_feeds():
    """Test syncing all feeds at once"""
    print("Testing sync all feeds...")
    result = sync_all_rss_feeds()
    print(f"  Total fetched: {result.get('total_fetched')}")
    print(f"  Total new items: {result.get('total_new_items')}")
    print(f"  Total skipped: {result.get('total_skipped_duplicates')}")
    print("✓ Sync all feeds works\n")

if __name__ == "__main__":
    try:
        test_feed_config()
        test_fetch_individual_feeds()
        test_sync_individual_feeds()
        test_sync_all_feeds()
        print("All RSS multi-feed tests passed! ✓")
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)