"""
Persistencia de propiedades scrapeadas en Supabase (tabla `tibesa_web_propiedades`).

Reutiliza la configuración de Supabase de `leads.supabase_client` (misma URL y
service_role key). El payload completo de cada scraper se guarda íntegro en la
columna JSONB `datos`, sin pérdida de datos por más que cada portal tenga su
propia estructura.
"""

import datetime
from typing import Any, Dict, List, Optional

import requests

from leads.supabase_client import SUPABASE_URL, SUPABASE_KEY

TABLA = "tibesa_web_propiedades"
TABLA_LOG = "tibesa_scrapeos_log"

# Portales conocidos (coincide con las claves de SCRAPERS_MAP en main.py)
FUENTES = ["paraiso_dorado", "lamudi", "mitula", "remax_sunset_eagle", "pincali", "propiedades_com", "casasyterrenos", "century21", "depreventa", "trovit", "mazatlan_br", "icasas", "spezia", "realtor", "buscatucasa"]


def _headers(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    headers = {
        "apikey": SUPABASE_KEY or "",
        "Authorization": f"Bearer {SUPABASE_KEY or ''}",
    }
    if extra:
        headers.update(extra)
    return headers


def _primera_imagen(prop: Dict[str, Any]) -> Optional[str]:
    """Devuelve la mejor URL/ruta de imagen disponible en el payload del scraper."""
    for key in ("imagenes", "imagenes_descargadas"):
        valor = prop.get(key)
        if isinstance(valor, list) and valor:
            return valor[0]
    return prop.get("imagen_url") or prop.get("imagen_principal")


def _map_row(fuente: str, prop: Dict[str, Any], idx: int) -> Dict[str, Any]:
    """Mapea el dict que devuelve un scraper a una fila de `tibesa_web_propiedades`."""
    analisis = prop.get("analisis_llm", {}) if isinstance(prop.get("analisis_llm"), dict) else {}
    # Fallback namespaced para evitar colisión con un property_id real numérico
    pid = prop.get("property_id")
    property_id = str(pid) if pid not in (None, "", 0) else (prop.get("url") or f"_row{idx}")
    return {
        "fuente": fuente,
        "property_id": property_id,
        "titulo": prop.get("titulo"),
        "precio": prop.get("precio"),
        "moneda": prop.get("moneda"),
        "ubicacion": prop.get("ubicacion"),
        "tipo_propiedad": prop.get("tipo_propiedad") or analisis.get("tipo_propiedad"),
        "zona": prop.get("zona"),
        "url": prop.get("url"),
        "imagen_principal": _primera_imagen(prop),
        "datos": prop,  # payload completo, forma propia de cada portal (sin pérdida)
        "scraped_at": datetime.datetime.utcnow().isoformat(),
    }


def upsert_propiedades(fuente: str, propiedades: List[Dict[str, Any]]) -> int:
    """
    Inserta o actualiza (UPSERT por `fuente, property_id`) las propiedades de un portal.
    Re-scrapear reemplaza los datos viejos sin dejar la tabla vacía.

    Devuelve la cantidad de filas enviadas. No lanza excepción: ante error solo
    imprime y devuelve 0, para no romper el streaming del scraping.
    """
    if not propiedades:
        return 0

    rows = [_map_row(fuente, prop, i) for i, prop in enumerate(propiedades, 1)]

    # Garantizar property_id único: Postgres ON CONFLICT no admite la misma fila
    # dos veces en un mismo comando. Conservamos la última aparición de cada id.
    unicos = {r["property_id"]: r for r in rows}
    if len(unicos) < len(rows):
        print(f"   ℹ {len(rows) - len(unicos)} propiedades con property_id duplicado fusionadas")
    rows = list(unicos.values())

    enviadas = 0
    headers = _headers({
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    })
    url = f"{SUPABASE_URL}/rest/v1/{TABLA}?on_conflict=fuente,property_id"

    # Enviar en lotes para no armar payloads gigantes (ej. 718 propiedades de Mitula)
    for inicio in range(0, len(rows), 200):
        lote = rows[inicio:inicio + 200]
        try:
            r = requests.post(url, headers=headers, json=lote, timeout=60)
            if r.status_code in (200, 201, 204):
                enviadas += len(lote)
            else:
                print(f"❌ Error guardando propiedades ({fuente}): {r.status_code} {r.text[:300]}")
        except Exception as e:
            print(f"❌ Excepción guardando propiedades ({fuente}): {e}")

    print(f"💾 {enviadas}/{len(rows)} propiedades de '{fuente}' guardadas en Supabase")
    return enviadas


def obtener_propiedades(fuente: Optional[str] = None, limit: int = 500) -> List[Dict[str, Any]]:
    """
    Devuelve el payload completo (columna `datos`) de las propiedades guardadas.
    Si se pasa `fuente`, filtra por ese portal. Pensado para alimentar al chat.
    """
    params = f"?select=datos&order=scraped_at.desc&limit={limit}"
    if fuente:
        params += f"&fuente=eq.{fuente}"
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/{TABLA}{params}", headers=_headers(), timeout=30)
        if not r.ok:
            print(f"❌ Error leyendo propiedades: {r.status_code} {r.text[:200]}")
            return []
        return [row["datos"] for row in r.json() if row.get("datos")]
    except Exception as e:
        print(f"❌ Excepción leyendo propiedades: {e}")
        return []


def registrar_scrapeo(
    fuente: str,
    total_propiedades: int,
    duracion_segundos: float,
    iniciado_at: Optional[str] = None,
    finalizado_at: Optional[str] = None,
) -> bool:
    """Registra una corrida de scraping en el historial (`tibesa_scrapeos_log`).
    No lanza excepción: ante error solo imprime, para no romper el streaming."""
    payload = {
        "fuente": fuente,
        "total_propiedades": total_propiedades,
        "duracion_segundos": round(duracion_segundos, 1),
        "iniciado_at": iniciado_at,
        "finalizado_at": finalizado_at or datetime.datetime.utcnow().isoformat(),
    }
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/{TABLA_LOG}",
            headers=_headers({"Content-Type": "application/json", "Prefer": "return=minimal"}),
            json=payload,
            timeout=30,
        )
        if r.status_code in (200, 201, 204):
            print(f"⏱️  Scrapeo de '{fuente}' registrado: {total_propiedades} props en {duracion_segundos:.0f}s")
            return True
        print(f"❌ Error registrando scrapeo ({fuente}): {r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"❌ Excepción registrando scrapeo ({fuente}): {e}")
    return False


def _duracion_log(fuente: str, ultimas: int = 10) -> Dict[str, Any]:
    """Devuelve duración promedio (últimas N corridas) y última duración de un portal."""
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/{TABLA_LOG}"
            f"?fuente=eq.{fuente}&select=duracion_segundos&order=finalizado_at.desc&limit={ultimas}",
            headers=_headers(),
            timeout=30,
        )
        filas = r.json() if r.ok else []
    except Exception:
        filas = []

    duraciones = [f["duracion_segundos"] for f in filas if f.get("duracion_segundos")]
    if not duraciones:
        return {"duracion_promedio_seg": None, "ultima_duracion_seg": None, "total_corridas": 0}
    return {
        "duracion_promedio_seg": round(sum(duraciones) / len(duraciones), 1),
        "ultima_duracion_seg": duraciones[0],
        "total_corridas": len(duraciones),
    }


def estado_propiedades() -> List[Dict[str, Any]]:
    """
    Devuelve, por portal: total de propiedades y fecha de última actualización.
    Alimenta el aviso de frescura del frontend ("actualizado hace X días").
    """
    estado: List[Dict[str, Any]] = []
    for fuente in FUENTES:
        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/{TABLA}"
                f"?fuente=eq.{fuente}&select=scraped_at&order=scraped_at.desc&limit=1",
                headers=_headers({"Prefer": "count=exact"}),
                timeout=30,
            )
            # El total viene en el header Content-Range: "0-0/123"
            total = 0
            content_range = r.headers.get("content-range", "")
            if "/" in content_range:
                try:
                    total = int(content_range.split("/")[-1])
                except ValueError:
                    total = 0
            filas = r.json() if r.ok else []
            ultima = filas[0]["scraped_at"] if filas else None
        except Exception as e:
            print(f"❌ Excepción consultando estado ({fuente}): {e}")
            total, ultima = 0, None

        estado.append({
            "fuente": fuente,
            "total_propiedades": total,
            "ultima_actualizacion": ultima,
            **_duracion_log(fuente),
        })
    return estado
