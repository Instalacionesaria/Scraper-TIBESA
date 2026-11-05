"""
Scraper de leads de LinkedIn vía Apify (peakydev/leads-scraper-ppe).

El actor recibe filtros tipo Apollo (job title / país / estado / total) y devuelve
contactos con email + LinkedIn. Aquí lo lanzamos en modo asíncrono y registramos
un webhook para procesar el dataset cuando termine.
"""

import os
import unicodedata
from typing import Any, Dict, List, Optional

from apify_client import ApifyClient


APIFY_TOKEN = os.getenv("APIFY_API_TOKEN")
ACTOR_ID = "peakydev/leads-scraper-ppe"

# El actor valida `personState` contra un enum cerrado con nombres en inglés
# (estilo Apollo, p.ej. "Mexico City"). Traducimos los alias frecuentes en
# español a su valor válido. Los nombres que ya vienen en inglés pasan directo;
# cualquier valor no aceptado se filtra luego con el reintento sin estado.
_STATE_ALIASES = {
    "ciudad de mexico": "Mexico City",
    "cdmx": "Mexico City",
    "distrito federal": "Mexico City",
    "df": "Mexico City",
}


def _normalize_state(value: str) -> str:
    """Normaliza el estado al valor que espera el actor (enum en inglés)."""
    v = value.strip()
    key = unicodedata.normalize("NFKD", v).encode("ascii", "ignore").decode().lower()
    return _STATE_ALIASES.get(key, v)


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
        run_input["personState"] = [_normalize_state(person_state)]

    webhook_url = f"{webhook_base_url}/api/leads/webhooks/linkedin"
    print(f"🚀 Iniciando LinkedIn scrape | title={person_title} | country={person_country} | state={person_state} | total={total_results}")
    print(f"🔗 Webhook LinkedIn: {webhook_url}")

    webhooks = [{
        "event_types": ["ACTOR.RUN.SUCCEEDED"],
        "request_url": webhook_url,
        "payload_template": f'{{"job_id": "{job_id}", "resource": {{{{resource}}}}}}',
    }]

    def _start(inp: Dict[str, Any]):
        return client.actor(ACTOR_ID).start(
            run_input=inp,
            memory_mbytes=512,
            webhooks=webhooks,
        )

    try:
        run = _start(run_input)
    except Exception as e:
        # Si el actor rechaza el estado (no está en su enum permitido),
        # reintentamos sin filtro de estado para no perder toda la búsqueda,
        # que igual filtra por país.
        if "personState" in str(e) and "personState" in run_input:
            print(f"⚠️ personState '{person_state}' no válido para el actor; reintentando sin estado.")
            run_input.pop("personState", None)
            run = _start(run_input)
        else:
            raise

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


_LEAD_KEYS = ("email", "lastName", "last_name", "title", "linkedinUrl", "linkedin_url", "companyName", "company_name")


def _is_notice(item: Dict[str, Any]) -> bool:
    """El actor mete avisos en el dataset como filas falsas (texto en `firstName`,
    sin email, cargo ni apellido). No son leads."""
    return not any(item.get(k) for k in _LEAD_KEYS)


def _traducir_aviso(texto: str) -> str:
    """Traduce los avisos del actor a un mensaje claro en español para el usuario."""
    t = texto.lower()
    if "exhausted all leads" in t:
        return ("Ya se descargaron todos los leads disponibles para esta misma búsqueda en una corrida anterior. "
                "El buscador no repite leads: cambia el cargo, el estado o el país para obtener leads nuevos.")
    if "no leads found" in t:
        return ("No hay leads con email para esta combinación de cargo, país y estado. "
                "Prueba un cargo más general (en inglés), otro estado, o deja el estado vacío.")
    if "delivered all" in t:
        return ("Se entregaron todos los leads disponibles para estos filtros "
                "(había menos de los que pediste).")
    return texto


def split_leads_y_avisos(dataset_items: List[Dict[str, Any]]):
    """Separa los leads reales de los avisos del actor. Devuelve (leads_items, aviso|None).
    Se ignora el aviso genérico de 'Leave Start Page empty' (es informativo, siempre sale)."""
    leads_items, avisos = [], []
    for item in dataset_items:
        if _is_notice(item):
            texto = (item.get("firstName") or item.get("first_name") or "").strip()
            if texto and "leave start page empty" not in texto.lower():
                avisos.append(_traducir_aviso(texto))
        else:
            leads_items.append(item)
    return leads_items, (avisos[-1] if avisos else None)


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
