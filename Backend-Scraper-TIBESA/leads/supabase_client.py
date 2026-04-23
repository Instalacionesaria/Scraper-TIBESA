"""
Helpers para interactuar con Supabase vía REST.

Centraliza la autenticación del service role y las operaciones sobre las tablas
`usuarios_scraper_tibesa` y `scraping_jobs_tibesa`.
"""

import datetime
import os
from typing import Any, Dict, Optional

import requests
from fastapi import HTTPException


SUPABASE_URL = os.getenv("SUPABASE_URL", "https://urxuebohedbjydwaedua.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def _headers(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    headers = {
        "apikey": SUPABASE_KEY or "",
        "Authorization": f"Bearer {SUPABASE_KEY or ''}",
    }
    if extra:
        headers.update(extra)
    return headers


def _json_headers() -> Dict[str, str]:
    return _headers({"Content-Type": "application/json", "Prefer": "return=representation"})


# ---------- Usuarios ----------

def get_user_by_email(correo: str) -> Dict[str, Any]:
    """Devuelve el usuario o lanza 404."""
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/usuarios_scraper_tibesa"
        f"?correo_electronico=eq.{correo}&select=*",
        headers=_headers(),
    )
    data = r.json() if r.ok else []
    if not data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    return data[0]


def authenticate_user(correo: str, password: str) -> Dict[str, Any]:
    """Valida credenciales y estado del usuario."""
    user = get_user_by_email(correo)
    if user.get("password") != password:
        raise HTTPException(status_code=401, detail="Contraseña incorrecta.")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Usuario inactivo.")
    return user


def get_user_stats(correo: str) -> Dict[str, Any]:
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/usuarios_scraper_tibesa"
        f"?correo_electronico=eq.{correo}"
        f"&select=total_leads_scrapeados,total_scraping_jobs,ultimo_scraping_at",
        headers=_headers(),
    )
    data = r.json() if r.ok else []
    if not data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    u = data[0]
    return {
        "total_leads_scrapeados": u.get("total_leads_scrapeados", 0),
        "total_scraping_jobs": u.get("total_scraping_jobs", 0),
        "ultimo_scraping_at": u.get("ultimo_scraping_at"),
    }


# ---------- Jobs ----------

def create_job(
    user_id: str,
    business_type: str,
    location: str,
    get_emails: bool = False,
    results_data: Optional[Dict[str, Any]] = None,
) -> str:
    """Crea un job en `scraping_jobs_tibesa` y devuelve su id."""
    payload: Dict[str, Any] = {
        "user_id": user_id,
        "status": "PENDING",
        "business_type": business_type,
        "location": location,
        "get_emails": get_emails,
        "get_business_model": False,
    }
    if results_data is not None:
        payload["results_data"] = results_data

    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/scraping_jobs_tibesa",
        headers=_json_headers(),
        json=payload,
    )
    if r.status_code != 201:
        print(f"❌ Error creando job: {r.status_code} {r.text}")
        raise HTTPException(status_code=500, detail=f"No se pudo registrar el trabajo. {r.text}")
    return r.json()[0]["id"]


def get_job(job_id: str, select: str = "*") -> Dict[str, Any]:
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/scraping_jobs_tibesa?id=eq.{job_id}&select={select}",
        headers=_headers(),
    )
    data = r.json() if r.ok else []
    if not data:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
    return data[0]


def update_job_run_id(job_id: str, run_id: str) -> None:
    """Asocia el run de Apify al job y lo marca como RUNNING."""
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/scraping_jobs_tibesa?id=eq.{job_id}",
        headers=_json_headers(),
        json={"apify_actor_run_id": run_id, "status": "RUNNING"},
    )
    print(f"🔗 Job {job_id} vinculado a Apify run {run_id}. Estado: RUNNING.")


def update_job_results(
    job_id: str,
    status: str,
    results: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
) -> bool:
    data: Dict[str, Any] = {"status": status}
    if error_message:
        data["error_message"] = error_message
    if results:
        data["results_data"] = results
        data["results_count"] = results.get("results_count", 0)
    if status == "COMPLETED":
        data["completed_at"] = datetime.datetime.utcnow().isoformat()

    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/scraping_jobs_tibesa?id=eq.{job_id}",
        headers=_json_headers(),
        json=data,
    )
    if r.status_code in (200, 204):
        return True
    print(f"❌ Error actualizando job {job_id}: {r.status_code} {r.text}")
    return False


def patch_job_results_data(job_id: str, results_data: Dict[str, Any]) -> bool:
    """Actualiza solo el campo results_data sin tocar el status."""
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/scraping_jobs_tibesa?id=eq.{job_id}",
        headers=_json_headers(),
        json={"results_data": results_data},
    )
    return r.status_code in (200, 204)
