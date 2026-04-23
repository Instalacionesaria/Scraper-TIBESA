"""
Scraper de Facebook Ads Library vía Apify (curious_coder/facebook-ads-library-scraper).
"""

import os
from typing import Any, Dict, List

from apify_client import ApifyClient


APIFY_TOKEN = os.getenv("APIFY_API_TOKEN")
ACTOR_ID = "curious_coder/facebook-ads-library-scraper"


def start_facebook_ads_scrape(scrape_url: str, webhook_base_url: str, job_id: str) -> str:
    """Lanza el actor de FB Ads y devuelve el run_id."""
    client = ApifyClient(APIFY_TOKEN)

    run_input: Dict[str, Any] = {
        "count": 1000,
        "scrapeAdDetails": False,
        "scrapePageAds.activeStatus": "all",
        "scrapePageAds.countryCode": "ALL",
        "urls": [{"url": scrape_url, "method": "GET"}],
    }

    webhook_url = f"{webhook_base_url}/api/leads/webhooks/facebook-ads"
    print(f"🚀 Iniciando FB Ads. URL: {scrape_url}")
    print(f"🔗 Webhook FB Ads: {webhook_url}")

    run = client.actor(ACTOR_ID).start(
        run_input=run_input,
        memory_mbytes=512,
        webhooks=[{
            "event_types": ["ACTOR.RUN.SUCCEEDED"],
            "request_url": webhook_url,
            "payload_template": f'{{"job_id": "{job_id}", "resource": {{{{resource}}}}}}',
        }],
    )
    return run["id"]


def build_facebook_ads_table_items(dataset_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extrae page_name / page_profile_uri / page_id de cada anuncio."""
    results: List[Dict[str, Any]] = []
    for item in dataset_items:
        snapshot = item.get("snapshot", {})
        results.append({
            "page_name": snapshot.get("page_name") or item.get("page_name"),
            "page_profile_uri": snapshot.get("page_profile_uri") or item.get("page_profile_uri"),
            "page_id": snapshot.get("page_id") or item.get("page_id"),
        })
    return results
