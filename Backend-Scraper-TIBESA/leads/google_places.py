"""
Scraper de Google Places vía Apify (compass/crawler-google-places).

Se dispara el actor en modo asíncrono y se registra un webhook para procesar
los resultados cuando Apify termine.
"""

import os
from typing import Any, Dict, List

from apify_client import ApifyClient


APIFY_TOKEN = os.getenv("APIFY_API_TOKEN")
ACTOR_ID = "compass/crawler-google-places"


def start_google_places_scrape(
    business_type: str,
    location: str,
    get_emails: bool,
    webhook_base_url: str,
    job_id: str,
) -> str:
    """Lanza el actor de Google Places y devuelve el run_id."""
    client = ApifyClient(APIFY_TOKEN)

    run_input: Dict[str, Any] = {
        "searchStringsArray": [business_type],
        "locationQuery": location,
        "maxCrawledPlaces": 1,
        "maxAutomaticZoomOut": 0,
        "language": "es",
        "maxImages": 0,
        "maxReviews": 0,
        "proxyConfiguration": {"useApifyProxy": True},
    }
    if get_emails:
        run_input["maximumLeadsEnrichmentRecords"] = 2

    webhook_url = f"{webhook_base_url}/api/leads/webhooks/google-places"
    print(f"🔗 Webhook Google Places: {webhook_url}")

    run = client.actor(ACTOR_ID).start(
        run_input=run_input,
        webhooks=[{
            "event_types": ["ACTOR.RUN.SUCCEEDED"],
            "request_url": webhook_url,
            "payload_template": f'{{"job_id": "{job_id}", "resource": {{{{resource}}}}}}',
        }],
    )
    return run["id"]


def build_final_leads(dataset_items: List[Dict[str, Any]], get_emails: bool) -> List[Dict[str, Any]]:
    """Construye la lista final de leads a partir de los items de Apify."""
    base_fields = [
        "title", "categoryName", "address", "neighborhood", "street",
        "website", "phone", "phoneUnformatted",
    ]
    enrichment_fields = [
        "fullName", "jobTitle", "email", "emails", "linkedinProfile",
        "mobileNumber", "companyName", "companyWebsite", "companyLinkedin",
        "companyPhoneNumber", "companySize", "industry", "city",
    ]

    results: List[Dict[str, Any]] = []
    for item in dataset_items:
        lead = {f: None for f in base_fields + enrichment_fields}
        for f in base_fields:
            if item.get(f):
                lead[f] = item.get(f)
        if get_emails and item.get("leadsEnrichment"):
            enrichment = item["leadsEnrichment"][0]
            for f in enrichment_fields:
                if enrichment.get(f):
                    lead[f] = enrichment.get(f)
        results.append(lead)
    return results
