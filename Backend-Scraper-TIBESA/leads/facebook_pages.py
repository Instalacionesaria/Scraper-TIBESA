"""
Scraper de Páginas de Facebook vía Apify (apify/facebook-pages-scraper).
"""

import os
from typing import Any, Dict, List

from apify_client import ApifyClient


APIFY_TOKEN = os.getenv("APIFY_API_TOKEN")
ACTOR_ID = "apify/facebook-pages-scraper"

DESIRED_FIELDS = [
    "facebookUrl", "likes", "title", "address", "pageId", "pageName",
    "pageUrl", "phone", "email", "website", "followers", "business_service_area",
]


def start_facebook_pages_scrape(page_urls: List[str], webhook_base_url: str, job_id: str) -> str:
    """Lanza el actor de FB Pages y devuelve el run_id. Deduplica URLs manteniendo orden."""
    client = ApifyClient(APIFY_TOKEN)

    unique_urls = list(dict.fromkeys(page_urls))
    if len(page_urls) != len(unique_urls):
        print(f"⚠️ Deduplicadas {len(page_urls) - len(unique_urls)} URLs de {len(page_urls)}")

    run_input: Dict[str, Any] = {
        "startUrls": [{"url": url, "method": "GET"} for url in unique_urls],
    }

    webhook_url = f"{webhook_base_url}/api/leads/webhooks/facebook-pages"
    print(f"🚀 Iniciando FB Pages con {len(unique_urls)} páginas únicas")
    print(f"🔗 Webhook FB Pages: {webhook_url}")

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


def build_facebook_pages_table_items(dataset_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extrae solo los campos relevantes de cada página scrapeada."""
    results: List[Dict[str, Any]] = []
    for item in dataset_items:
        results.append({f: item.get(f) for f in DESIRED_FIELDS})
    return results
