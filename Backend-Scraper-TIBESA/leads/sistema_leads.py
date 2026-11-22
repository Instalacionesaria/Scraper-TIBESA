"""
Cliente para el "Sistema de Leads" (webhook n8n de ARIA IA).

El webhook recibe prospectos uno por uno y hace un análisis con IA de cada uno,
así que cada envío tarda varios segundos (100 leads ≈ 12-17 min en serie). Por
eso se envían en paralelo (CONCURRENCIA) y el endpoint corre esto en segundo
plano, informando el progreso con `on_progress`.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

import requests


SISTEMA_LEADS_URL = "https://tibesa-next.vercel.app/api/webhooks/prospectos"
# Envíos simultáneos al webhook. Moderado: cada prospecto dispara un análisis IA
# en el receptor y no queremos saturarlo.
CONCURRENCIA = 3

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


def _enviar_uno(lead: Dict[str, Any]) -> Optional[str]:
    """Envía un lead. Devuelve None si salió bien o el texto del error."""
    payload = format_lead_for_sistema(lead)
    if not payload.get("title"):
        return "Lead sin título — descartado"
    try:
        r = requests.post(
            SISTEMA_LEADS_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60,
        )
        if r.ok:
            return None
        return f"HTTP {r.status_code}: {r.text[:120]}"
    except requests.RequestException as e:
        return str(e)[:120]


def send_leads_to_sistema(
    leads: List[Dict[str, Any]],
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> Dict[str, Any]:
    """Envía cada lead al webhook (en paralelo) y agrega estadísticas.

    `on_progress(enviados, fallidos)` se llama tras cada lead procesado.
    """
    sent = 0
    failed = 0
    errors: List[str] = []
    lock = threading.Lock()

    def _procesar(lead: Dict[str, Any]) -> None:
        nonlocal sent, failed
        error = _enviar_uno(lead)
        with lock:
            if error is None:
                sent += 1
            else:
                failed += 1
                errors.append(error)
            s_, f_ = sent, failed
        if on_progress:
            try:
                on_progress(s_, f_)
            except Exception:
                pass

    with ThreadPoolExecutor(max_workers=CONCURRENCIA) as pool:
        list(pool.map(_procesar, leads))

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
        }
    return {
        "success": True,
        "message": f"{sent} de {total} leads enviados. {failed} fallaron.",
        "leads_sent": sent,
        "leads_failed": failed,
        "errors": errors[:5],
    }
