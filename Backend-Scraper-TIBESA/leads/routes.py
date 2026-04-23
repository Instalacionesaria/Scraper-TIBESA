"""
Endpoints FastAPI del módulo de leads.

Prefijo: /api/leads

Agrupa:
  - Google Places (búsqueda de leads empresariales)
  - Facebook Ads Library
  - Facebook Pages
  - Envío a CRM de TIBESA
  - Webhooks que Apify llama cuando termina un actor
  - Consulta / cancelación / sync manual de jobs
"""

import os
import traceback
from typing import Any, Dict

from apify_client import ApifyClient
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from . import crm_tibesa, facebook_ads, facebook_pages, google_places
from .models import (
    ApifyWebhookPayload,
    EnviarCRMRequest,
    FacebookAdsRequest,
    FacebookPagesRequest,
    GooglePlacesRequest,
)
from .supabase_client import (
    authenticate_user,
    create_job,
    get_job,
    get_user_by_email,
    get_user_stats,
    patch_job_results_data,
    update_job_results,
    update_job_run_id,
)


APIFY_TOKEN = os.getenv("APIFY_API_TOKEN")
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "")


router = APIRouter(prefix="/api/leads", tags=["leads"])


# ============================================================================
# GOOGLE PLACES — Búsqueda de leads empresariales
# ============================================================================

@router.post("/google-places/start")
async def start_google_places(request: GooglePlacesRequest) -> Dict[str, Any]:
    """Inicia un scraping de Google Places vía Apify."""
    user = authenticate_user(request.correo_electronico, request.password)
    print(f"✅ Usuario autenticado: {request.correo_electronico}")

    job_id = create_job(
        user_id=user["id"],
        business_type=request.businessType,
        location=request.location,
        get_emails=request.getEmails,
    )

    try:
        run_id = google_places.start_google_places_scrape(
            business_type=request.businessType,
            location=request.location,
            get_emails=request.getEmails,
            webhook_base_url=WEBHOOK_BASE_URL,
            job_id=job_id,
        )
        update_job_run_id(job_id, run_id)
    except Exception as e:
        update_job_results(job_id, "FAILED", error_message=str(e))
        raise HTTPException(status_code=502, detail=f"Error iniciando Apify: {e}")

    return {"status": "success", "message": "Tu búsqueda ha comenzado.", "jobId": job_id}


# ============================================================================
# FACEBOOK ADS LIBRARY
# ============================================================================

@router.post("/facebook/ads/start")
async def start_facebook_ads(request: FacebookAdsRequest) -> Dict[str, Any]:
    """Scrapea la biblioteca de anuncios de Facebook."""
    scrape_url = request.get_url()
    if not scrape_url:
        raise HTTPException(status_code=400, detail="Falta la URL de Facebook Ads.")

    user = get_user_by_email(request.correo_electronico)

    job_id = create_job(
        user_id=user["id"],
        business_type="Facebook Ads",
        location=scrape_url,
    )

    try:
        run_id = facebook_ads.start_facebook_ads_scrape(
            scrape_url=scrape_url,
            webhook_base_url=WEBHOOK_BASE_URL,
            job_id=job_id,
        )
        update_job_run_id(job_id, run_id)
    except Exception as e:
        update_job_results(job_id, "FAILED", error_message=str(e))
        raise HTTPException(status_code=502, detail=f"Error iniciando FB Ads: {e}")

    print(f"✅ FB Ads iniciado. Job: {job_id} | Run: {run_id}")
    return {"status": "success", "message": "El scraping de Facebook Ads ha comenzado.", "jobId": job_id}


# ============================================================================
# FACEBOOK PAGES
# ============================================================================

@router.post("/facebook/pages/start")
async def start_facebook_pages(request: FacebookPagesRequest) -> Dict[str, Any]:
    """Scrapea un lote de páginas de Facebook."""
    page_urls = request.get_page_urls()
    if not page_urls:
        raise HTTPException(
            status_code=400,
            detail="No se encontraron páginas válidas (falta page_profile_uri en cada item).",
        )

    user = get_user_by_email(request.correo_electronico)

    job_id = create_job(
        user_id=user["id"],
        business_type="Facebook Pages (Bulk)",
        location=f"{len(page_urls)} páginas",
        results_data={"original_pages": request.get_original_pages_data()},
    )

    try:
        run_id = facebook_pages.start_facebook_pages_scrape(
            page_urls=page_urls,
            webhook_base_url=WEBHOOK_BASE_URL,
            job_id=job_id,
        )
        update_job_run_id(job_id, run_id)
    except Exception as e:
        update_job_results(job_id, "FAILED", error_message=str(e))
        raise HTTPException(status_code=502, detail=f"Error iniciando FB Pages: {e}")

    print(f"✅ FB Pages iniciado. Job: {job_id} | Run: {run_id}")
    return {
        "status": "success",
        "message": "El scraping de las páginas de Facebook ha comenzado.",
        "jobId": job_id,
        "job_id": job_id,  # compat snake_case
    }


# ============================================================================
# ENVÍO A CRM DE TIBESA
# ============================================================================

@router.post("/crm/send")
async def send_to_crm(request: EnviarCRMRequest) -> Dict[str, Any]:
    """Envía los leads de un job completado al CRM de TIBESA."""
    ok, err = crm_tibesa.validate_etiqueta(request.etiqueta)
    if not ok:
        raise HTTPException(status_code=400, detail=err)

    user = get_user_by_email(request.correo_electronico)
    job = get_job(request.job_id)

    if job.get("user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="No tienes permiso sobre este trabajo.")
    if job.get("status") != "COMPLETED":
        raise HTTPException(
            status_code=400,
            detail=f"El trabajo no está completado. Estado: {job.get('status')}",
        )

    results_data = job.get("results_data") or {}
    leads = results_data.get("data") or []
    if not leads:
        raise HTTPException(status_code=400, detail="El trabajo no tiene resultados para enviar.")

    print(f"📊 {len(leads)} leads a enviar al CRM")

    formatted = crm_tibesa.format_leads_for_crm(leads)
    result = crm_tibesa.send_leads_to_crm(
        leads=formatted,
        etiqueta=request.etiqueta,
        user_email=request.correo_electronico,
        job_id=request.job_id,
    )

    if result["success"]:
        results_data.update({
            "enviado_a_crm": True,
            "crm_etiqueta": request.etiqueta,
            "crm_fecha_envio": __import__("datetime").datetime.utcnow().isoformat(),
        })
        patch_job_results_data(request.job_id, results_data)

    return {
        "status": "success" if result["success"] else "error",
        "message": result["message"],
        "leads_sent": result["leads_sent"],
        "etiqueta": request.etiqueta,
        "job_id": request.job_id,
    }


# ============================================================================
# JOBS — consulta / cancelación / sync
# ============================================================================

@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str) -> Dict[str, Any]:
    """Devuelve el estado y resultados de un job."""
    job = get_job(job_id, select="status,results_data,results_count")
    response: Dict[str, Any] = {"status": job.get("status")}
    if job.get("status") == "COMPLETED" and job.get("results_data"):
        response["results"] = job["results_data"]
        response["results_count"] = job.get("results_count", 0)
    return response


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> Dict[str, Any]:
    """Cancela un job en progreso (aborta el actor en Apify también)."""
    job = get_job(job_id, select="apify_actor_run_id,status")
    if job.get("status") not in ("PENDING", "RUNNING"):
        raise HTTPException(
            status_code=400,
            detail=f"No se puede cancelar. Estado actual: {job.get('status')}",
        )

    run_id = job.get("apify_actor_run_id")
    if run_id:
        try:
            ApifyClient(APIFY_TOKEN).run(run_id).abort()
            print(f"✅ Apify run {run_id} cancelado")
        except Exception as e:
            print(f"⚠️  Error cancelando en Apify: {e}")

    update_job_results(job_id, "CANCELLED", error_message="Trabajo cancelado por el usuario")
    return {"status": "success", "message": "Trabajo cancelado.", "jobId": job_id}


@router.post("/jobs/{job_id}/sync")
async def sync_job(job_id: str) -> Dict[str, Any]:
    """Sincroniza manualmente el estado del job con Apify (por si el webhook nunca llegó)."""
    job = get_job(job_id)
    run_id = job.get("apify_actor_run_id")
    current_status = job.get("status")

    if not run_id:
        raise HTTPException(status_code=400, detail="El job no tiene run_id de Apify asociado.")

    client = ApifyClient(APIFY_TOKEN)
    run_info = client.run(run_id).get()
    apify_status = run_info.get("status")
    dataset_id = run_info.get("defaultDatasetId")

    print(f"📊 Sync job {job_id}: BD={current_status} | Apify={apify_status}")

    if apify_status == "SUCCEEDED":
        if current_status == "COMPLETED":
            return {"status": "already_completed", "apify_status": apify_status}
        await _process_google_places_results(job_id, dataset_id)
        return {
            "status": "success",
            "message": "Job sincronizado y procesado.",
            "apify_status": apify_status,
            "previous_status": current_status,
        }
    if apify_status == "FAILED":
        err = run_info.get("statusMessage", "Error desconocido en Apify")
        update_job_results(job_id, "FAILED", error_message=err)
        return {"status": "failed", "apify_status": apify_status, "error": err}
    if apify_status in ("READY", "RUNNING"):
        return {"status": "in_progress", "apify_status": apify_status}
    return {"status": "unknown", "apify_status": apify_status}


@router.get("/user-stats/{correo}")
async def user_stats(correo: str) -> Dict[str, Any]:
    """Estadísticas agregadas del usuario."""
    return get_user_stats(correo)


# ============================================================================
# WEBHOOKS — los invoca Apify cuando un actor termina
# ============================================================================

@router.post("/webhooks/google-places")
async def webhook_google_places(
    payload: ApifyWebhookPayload,
    background_tasks: BackgroundTasks,
    request: Request,
):
    """Webhook de Apify: Google Places SUCCEEDED."""
    try:
        body = await request.body()
        print(f"🔔 Webhook Google Places | Job: {payload.job_id} | Dataset: {payload.resource.defaultDatasetId}")
        print(f"📦 Payload: {body.decode() if body else 'vacío'}")
        background_tasks.add_task(
            _process_google_places_results,
            payload.job_id,
            payload.resource.defaultDatasetId,
        )
        return {"status": "webhook received", "job_id": payload.job_id}
    except Exception as e:
        print(f"❌ Error webhook Google Places: {e}")
        traceback.print_exc()
        return {"status": "error", "detail": str(e)}


@router.post("/webhooks/facebook-ads")
async def webhook_facebook_ads(payload: ApifyWebhookPayload, background_tasks: BackgroundTasks):
    """Webhook de Apify: Facebook Ads SUCCEEDED."""
    print(f"🔔 Webhook FB Ads | Job: {payload.job_id}")
    background_tasks.add_task(
        _process_facebook_ads_results,
        payload.job_id,
        payload.resource.defaultDatasetId,
    )
    return {"status": "webhook received"}


@router.post("/webhooks/facebook-pages")
async def webhook_facebook_pages(payload: ApifyWebhookPayload, background_tasks: BackgroundTasks):
    """Webhook de Apify: Facebook Pages SUCCEEDED."""
    print(f"🔔 Webhook FB Pages | Job: {payload.job_id}")
    background_tasks.add_task(
        _process_facebook_pages_results,
        payload.job_id,
        payload.resource.defaultDatasetId,
    )
    return {"status": "webhook received"}


# ============================================================================
# PROCESADORES EN BACKGROUND
# ============================================================================

async def _process_google_places_results(job_id: str, dataset_id: str) -> None:
    try:
        print(f"🔄 Procesando Google Places. Job={job_id} Dataset={dataset_id}")
        job = get_job(
            job_id,
            select="*,usuarios_scraper_tibesa(correo_electronico)",
        )

        items = ApifyClient(APIFY_TOKEN).dataset(dataset_id).list_items().items
        print(f"📊 {len(items)} items de Apify")

        leads = google_places.build_final_leads(items, job.get("get_emails"))
        output = {"data": leads, "results_count": len(leads)}

        if update_job_results(job_id, "COMPLETED", results=output):
            print(f"🏁 Google Places job {job_id} completado. {len(leads)} leads.")
    except Exception as e:
        print(f"❌ Error procesando Google Places job {job_id}: {e}")
        traceback.print_exc()
        try:
            update_job_results(job_id, "FAILED", error_message=str(e))
        except Exception:
            pass


async def _process_facebook_ads_results(job_id: str, dataset_id: str) -> None:
    try:
        print(f"🔄 Procesando FB Ads. Job={job_id} Dataset={dataset_id}")
        items = ApifyClient(APIFY_TOKEN).dataset(dataset_id).list_items().items
        print(f"📊 {len(items)} items de Apify")

        # Detectar error del actor en el primer item
        if items and "error" in items[0]:
            err = items[0].get("error", "Error desconocido")
            print(f"❌ Actor error: {err}")
            update_job_results(job_id, "FAILED", error_message=str(err))
            return

        data = facebook_ads.build_facebook_ads_table_items(items)
        output = {"data": data, "results_count": len(data)}
        update_job_results(job_id, "COMPLETED", results=output)
        print(f"🏁 FB Ads job {job_id} completado. {len(data)} anuncios.")
    except Exception as e:
        print(f"❌ Error procesando FB Ads job {job_id}: {e}")
        update_job_results(job_id, "FAILED", error_message=str(e))


async def _process_facebook_pages_results(job_id: str, dataset_id: str) -> None:
    """Empareja los datos scrapeados con los originales del frontend, manteniendo el orden."""
    try:
        print(f"🔄 Procesando FB Pages. Job={job_id} Dataset={dataset_id}")
        job = get_job(job_id, select="results_data")
        original_pages = (job.get("results_data") or {}).get("original_pages", [])
        print(f"📋 Originales: {len(original_pages)}")

        items = ApifyClient(APIFY_TOKEN).dataset(dataset_id).list_items().items
        print(f"📊 Scrapeadas: {len(items)}")

        scraped = facebook_pages.build_facebook_pages_table_items(items)
        scraped_map = {(s.get("pageUrl") or s.get("facebookUrl")): s for s in scraped}

        matched = []
        for original in original_pages:
            uri = original.get("page_profile_uri")
            matched.append({**original, **(scraped_map.get(uri) or {})})

        output = {"data": matched, "results_count": len(matched)}
        update_job_results(job_id, "COMPLETED", results=output)
        print(f"🏁 FB Pages job {job_id} completado. {len(matched)} páginas.")
    except Exception as e:
        print(f"❌ Error procesando FB Pages job {job_id}: {e}")
        update_job_results(job_id, "FAILED", error_message=str(e))
