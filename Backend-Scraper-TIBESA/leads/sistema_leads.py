"""
Cliente para el "Sistema de Leads" (webhook n8n de ARIA IA).

El webhook recibe prospectos uno por uno; aquí iteramos los leads del job,
los mapeamos al formato esperado y agregamos los resultados.
"""

from typing import Any, Dict, List

import requests


SISTEMA_LEADS_URL = "https://tibesa-next.vercel.app/api/webhooks/prospectos"

# Campos aceptados por el endpoint de prospectos.
_ALLOWED_FIELDS = {
    "title",
    "phone",
    "phoneUnformatted",
    "mobileNumber",
    "email",
    "emails",
    "website",
    "address",
    "neighborhood",
    "city",
    "categoryName",
    "fullName",
    "jobTitle",
    "companyName",
    "industry",
    "linkedinProfile",
}

# Alias: si el campo del lead no coincide con los nombres esperados,
# probamos con estos alternativos antes de descartar.
_TITLE_ALIASES = ("title", "name", "page_name", "businessName", "pageName")
_ADDRESS_ALIASES = ("address", "street", "location")


def _first(d: Dict[str, Any], keys) -> Any:
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return None


def format_lead_for_sistema(lead: Dict[str, Any]) -> Dict[str, Any]:
    """Mapea un lead scrapeado al formato de prospectos del Sistema de Leads."""
    out: Dict[str, Any] = {}

    for field in _ALLOWED_FIELDS:
        value = lead.get(field)
        if value:
            out[field] = value

    # Title es requerido → intentamos aliases.
    if not out.get("title"):
        alt_title = _first(lead, _TITLE_ALIASES)
        if alt_title:
            out["title"] = alt_title

    # Address puede venir como "street" o "location"
    if not out.get("address"):
        alt_addr = _first(lead, _ADDRESS_ALIASES)
        if alt_addr and not isinstance(alt_addr, dict):
            out["address"] = alt_addr

    return out


def send_leads_to_sistema(leads: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Envía cada lead al webhook y agrega estadísticas."""
    sent = 0
    failed = 0
    errors: List[str] = []
    last_response: Dict[str, Any] = {}

    for lead in leads:
        payload = format_lead_for_sistema(lead)
        if not payload.get("title"):
            failed += 1
            errors.append("Lead sin título — descartado")
            continue
        try:
            r = requests.post(
                SISTEMA_LEADS_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            if r.ok:
                sent += 1
                try:
                    last_response = r.json()
                except Exception:
                    last_response = {"text": r.text[:200]}
            else:
                failed += 1
                errors.append(f"HTTP {r.status_code}: {r.text[:120]}")
        except requests.RequestException as e:
            failed += 1
            errors.append(str(e)[:120])

    total = sent + failed
    if sent == 0:
        return {
            "success": False,
            "message": f"No se pudo enviar ningún lead al Sistema. {failed} fallaron.",
            "leads_sent": 0,
            "leads_failed": failed,
            "errors": errors[:5],
        }
    if failed == 0:
        return {
            "success": True,
            "message": f"{sent} leads enviados al Sistema de Leads.",
            "leads_sent": sent,
            "leads_failed": 0,
            "last_response": last_response,
        }
    return {
        "success": True,
        "message": f"{sent} de {total} leads enviados. {failed} fallaron.",
        "leads_sent": sent,
        "leads_failed": failed,
        "errors": errors[:5],
        "last_response": last_response,
    }
