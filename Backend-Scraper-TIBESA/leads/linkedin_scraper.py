"""
Scraper de leads de LinkedIn vía Apify (peakydev/leads-scraper-ppe).

El actor recibe filtros tipo Apollo (job title / país / estado / total) y devuelve
contactos con email + LinkedIn. Aquí lo lanzamos en modo asíncrono y registramos
un webhook para procesar el dataset cuando termine.
"""

import os
from typing import Any, Dict, List, Optional

from apify_client import ApifyClient


APIFY_TOKEN = os.getenv("APIFY_API_TOKEN")
ACTOR_ID = "peakydev/leads-scraper-ppe"


def start_linkedin_scrape(
    person_title: str,
    person_country: str,
    person_state: Optional[str],
    total_results: int,
    webhook_base_url: str,
    job_id: str,
) -> str:
    """Lanza el actor de LinkedIn leads y devuelve el run_id."""
    client = ApifyClient(APIFY_TOKEN)

    run_input: Dict[str, Any] = {
        "personTitle": [person_title] if person_title else [],
        "personCountry": [person_country] if person_country else [],
        "totalResults": int(total_results) if total_results else 100,
        "includeEmails": True,
    }
    if person_state and person_state.strip():
        run_input["personState"] = [person_state.strip()]

    webhook_url = f"{webhook_base_url}/api/leads/webhooks/linkedin"
    print(f"🚀 Iniciando LinkedIn scrape | title={person_title} | country={person_country} | state={person_state} | total={total_results}")
    print(f"🔗 Webhook LinkedIn: {webhook_url}")

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


def _full_name(item: Dict[str, Any]) -> str:
    first = (item.get("first_name") or item.get("firstName") or "").strip()
    last = (item.get("last_name") or item.get("lastName") or "").strip()
    direct = (item.get("name") or item.get("fullName") or "").strip()
    if direct:
        return direct
    return f"{first} {last}".strip()


def _pick(item: Dict[str, Any], *keys: str) -> Any:
    for k in keys:
        v = item.get(k)
        if v:
            return v
    return None


def build_final_leads(dataset_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Mapea los items del actor a un schema homogéneo (camelCase) compatible con
    el envío al CRM de TIBESA y al Sistema de Leads."""
    results: List[Dict[str, Any]] = []
    for item in dataset_items:
        full_name = _full_name(item)
        email = _pick(item, "email", "work_email", "personal_email")
        phone = _pick(item, "phone", "mobile", "mobile_number", "phoneNumber")
        linkedin = _pick(item, "linkedin_url", "linkedinUrl", "linkedin", "linkedinProfile")
        company = _pick(item, "company_name", "companyName", "organization_name", "company")
        job_title = _pick(item, "title", "job_title", "jobTitle", "position")
        industry = _pick(item, "industry", "company_industry")
        country = _pick(item, "country", "person_country", "personCountry")
        state = _pick(item, "state", "person_state", "personState")
        city = _pick(item, "city", "person_city")
        seniority = _pick(item, "seniority")
        size = _pick(item, "company_size", "companySize", "employee_size")
        domain = _pick(item, "company_domain", "companyDomain", "website")

        lead = {
            # Para CRM (lee `title` como name, `companyName`, `jobTitle`, etc.)
            "title": full_name or company or "",
            "fullName": full_name,
            "email": email,
            "phone": phone,
            "mobileNumber": phone,
            "companyName": company,
            "jobTitle": job_title,
            "industry": industry,
            "categoryName": industry,
            "linkedinProfile": linkedin,
            "city": city or state,
            "neighborhood": state,
            "country": country,
            "address": ", ".join([x for x in (city, state, country) if x]) or None,
            # Extras
            "seniority": seniority,
            "companySize": size,
            "website": domain,
        }
        results.append(lead)
    return results
