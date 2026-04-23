"""
Envío de leads al CRM de TIBESA (sandboxapi.bienesraicestibesa.mx).

El CRM espera multipart/form-data con los campos requeridos: name, email, phone, source.
"""

import os
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple

import requests


CRM_API_URL = "https://sandboxapi.bienesraicestibesa.mx/contacts/createContact"
CRM_API_TOKEN = os.getenv("CRM_TIBESA_API_TOKEN")


def validate_etiqueta(etiqueta: str) -> Tuple[bool, str]:
    """Valida formato de la etiqueta (máx. 30 chars, caracteres permitidos)."""
    if not etiqueta or not etiqueta.strip():
        return False, "La etiqueta no puede estar vacía"
    if len(etiqueta) > 30:
        return False, "La etiqueta no puede exceder 30 caracteres"
    if not re.match(r'^[a-zA-Z0-9\s\-,áéíóúÁÉÍÓÚñÑ]+$', etiqueta):
        return False, "La etiqueta solo puede contener letras, números, espacios, guiones y comas"
    return True, ""


def format_leads_for_crm(raw_leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Limpia campos vacíos y añade metadatos."""
    formatted: List[Dict[str, Any]] = []
    for lead in raw_leads:
        clean = {k: v for k, v in lead.items() if v not in (None, "", [])}
        clean["source"] = "ARIA Scraper"
        clean["import_date"] = datetime.utcnow().isoformat()
        formatted.append(clean)
    return formatted


def send_leads_to_crm(
    leads: List[Dict[str, Any]],
    etiqueta: str,
    user_email: str,
    job_id: str,
) -> Dict[str, Any]:
    """Envía los leads uno por uno al CRM. Devuelve un resumen con sent/failed/skipped."""
    if not CRM_API_TOKEN:
        return {"success": False, "message": "Token del CRM no configurado", "leads_sent": 0, "leads_failed": 0}
    if not leads:
        return {"success": False, "message": "No hay leads para enviar", "leads_sent": 0, "leads_failed": 0}

    print(f"📤 Enviando {len(leads)} leads al CRM. Etiqueta: '{etiqueta}' | Usuario: {user_email}")

    sent = failed = skipped = 0
    errors: List[str] = []

    for idx, lead in enumerate(leads, 1):
        try:
            name = (lead.get("title") or "").strip()
            if not name:
                skipped += 1
                print(f"  ⏭️  Lead {idx}/{len(leads)} omitido: sin nombre")
                continue

            email = (lead.get("email") or "").strip() or "sin-email@tibesa.com"
            phone = (lead.get("phone") or lead.get("phoneUnformatted") or "").strip() or "No disponible"

            form_data = {
                # Requeridos
                "name": name,
                "email": email,
                "phone": phone,
                "source": "ariaIA",
                # Opcionales
                "company": lead.get("companyName") or lead.get("title", ""),
                "address": lead.get("address", ""),
                "website": lead.get("website", ""),
                "tag": etiqueta,
                "job_id": job_id,
                "import_date": datetime.utcnow().isoformat(),
                "category": lead.get("categoryName", ""),
                "neighborhood": lead.get("neighborhood", ""),
                "linkedin": lead.get("linkedinProfile", ""),
                "job_title": lead.get("jobTitle", ""),
            }
            # Eliminar vacíos salvo requeridos
            form_data = {
                k: v for k, v in form_data.items()
                if (v and str(v).strip()) or k in ("name", "email", "phone", "source")
            }

            files_data = {k: (None, str(v)) for k, v in form_data.items()}

            r = requests.post(
                CRM_API_URL,
                files=files_data,
                headers={"Authorization": CRM_API_TOKEN},
                timeout=60,
            )

            if r.status_code in (200, 201):
                sent += 1
                print(f"  ✅ {idx}/{len(leads)}: {name} ({email})")
            else:
                failed += 1
                msg = f"Lead {idx} ({name}): {r.status_code} - {r.text[:100]}"
                errors.append(msg)
                print(f"  ❌ {msg}")

        except Exception as e:
            failed += 1
            msg = f"Lead {idx}: {e}"
            errors.append(msg)
            print(f"  ❌ {msg}")

    message = _build_summary_message(sent, failed, skipped)
    result = {
        "success": sent > 0,
        "message": message,
        "leads_sent": sent,
        "leads_failed": failed,
        "leads_skipped": skipped,
    }
    if errors:
        result["errors"] = errors[:10]

    print(f"🏁 CRM TIBESA: {sent} enviados | {failed} fallidos | {skipped} omitidos")
    return result


def _build_summary_message(sent: int, failed: int, skipped: int) -> str:
    if skipped:
        if sent and not failed:
            return f"Se enviaron {sent} leads exitosamente. {skipped} omitidos por falta de nombre"
        if sent and failed:
            return f"Se enviaron {sent} leads. {failed} fallaron y {skipped} omitidos por falta de nombre"
        if failed and not sent:
            return f"No se pudo enviar ningún lead. {failed} fallaron y {skipped} omitidos"
        return f"Todos los leads ({skipped}) fueron omitidos por falta de nombre"
    if not failed:
        return f"Se enviaron {sent} leads exitosamente al CRM de TIBESA"
    if not sent:
        return f"No se pudo enviar ningún lead al CRM. {failed} fallaron"
    return f"Se enviaron {sent} leads exitosamente. {failed} fallaron"
