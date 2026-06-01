"""
API REST para el Scraper de Propiedades - Multi-Sitio
Levanta endpoints para conectar con el Frontend
Soporta SSE (Server-Sent Events) para streaming en tiempo real
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from typing import List, Optional
import json
import os
import time
import random
from pathlib import Path
from datetime import datetime
import asyncio
from dotenv import load_dotenv

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage

# Importar scrapers
from scrapers.paraiso_dorado import ParaisoDoradoScraper
from scrapers.lamudi import LamudiScraper
from scrapers.mitula import MitulaScraper
from scrapers.remax_sunset_eagle import RemaxSunsetEagleScraper
import aiohttp
from utils.agente_propiedades import procesar_propiedad_con_llm
from utils.propiedades_db import upsert_propiedades, obtener_propiedades, estado_propiedades, registrar_scrapeo
from playwright.async_api import async_playwright

# Brochure generator
from brochure.generator import generar_brochure

# Módulo de Leads (Google Places, Facebook Ads/Pages, CRM TIBESA)
from leads.routes import router as leads_router

load_dotenv()

# Inicializar FastAPI
app = FastAPI(
    title="API Scraper de Propiedades Multi-Sitio",
    description="API con streaming en tiempo real para scrapear propiedades inmobiliarias",
    version="3.0.0"
)

# ========================================
# CONFIGURACIÓN DE SCRAPERS
# ========================================

SCRAPERS_MAP = {
    'paraiso_dorado': {
        'class': ParaisoDoradoScraper,
        'domain': 'paraisodorado.com.mx',
        'name': 'Paraíso Dorado',
        'listado_url': 'https://paraisodorado.com.mx/es/propiedades',
    },
    'lamudi': {
        'class': LamudiScraper,
        'domain': 'www.lamudi.com.mx',
        'name': 'Lamudi',
        'listado_url': 'https://www.lamudi.com.mx/sinaloa/mazatlan/for-sale/',
    },
    'mitula': {
        'class': MitulaScraper,
        'domain': 'casas.mitula.mx',
        'name': 'Mitula',
        'listado_url': 'https://casas.mitula.mx/casas/casas-mazatlan',
        'scrape_from_listing': True,  # Indica que se scrapea directo del listado
    },
    'remax_sunset_eagle': {
        'class': RemaxSunsetEagleScraper,
        'domain': 'es.remaxsunseteagle.com',
        'name': 'RE/MAX Sunset Eagle',
        'listado_url': 'https://es.remaxsunseteagle.com/propiedades-mazatlan/',
        'is_remax': True,  # Soporta filtro por zona
    },
}

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar rutas del módulo de leads (Google Places, Facebook Ads/Pages, CRM TIBESA)
app.include_router(leads_router)

# Directorios
DATA_DIR = Path("data")
JSON_DIR = DATA_DIR / "json"
IMAGES_DIR = DATA_DIR / "imagenes"

JSON_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# Propiedades scrapeadas en paralelo en los scrapers de detalle (Lamudi, Paraíso).
# 3 = más conservador para reducir el riesgo de bloqueo anti-bot (Lamudi).
CONCURRENCIA_DETALLE = 3
# Pausa aleatoria (segundos) antes de cada propiedad, para parecer humano y no
# golpear al sitio en ráfagas sincronizadas.
DELAY_MIN, DELAY_MAX = 1.0, 3.5


# ========================================
# HELPERS: Extraer URLs de propiedades
# ========================================

async def extraer_urls_del_listado(site_id: str) -> List[str]:
    """Navega el listado de un sitio y extrae todas las URLs de propiedades"""
    config = SCRAPERS_MAP[site_id]

    if site_id == 'lamudi':
        return await _extraer_urls_lamudi(config)
    else:
        return await _extraer_urls_paraiso_dorado(config)


async def _extraer_urls_paraiso_dorado(config: dict) -> List[str]:
    """Extractor de URLs específico para Paraíso Dorado"""
    urls = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            base_url = config['listado_url']
            await page.goto(base_url, wait_until='networkidle', timeout=60000)
            await page.wait_for_timeout(2000)

            # Detectar total de páginas
            botones_pagina = await page.query_selector_all('nav[aria-label*="pagination"] button')
            num_paginas = 0
            for boton in botones_pagina:
                texto = await boton.inner_text()
                if texto.strip().isdigit():
                    num_paginas = max(num_paginas, int(texto.strip()))
            if num_paginas == 0:
                num_paginas = 12

            for num_pagina in range(1, num_paginas + 1):
                if num_pagina > 1:
                    selector_boton = f'nav[aria-label*="pagination"] button:has-text("{num_pagina}")'
                    boton = await page.query_selector(selector_boton)
                    if boton:
                        await boton.click()
                        await page.wait_for_timeout(2000)
                    else:
                        continue

                # Scroll para cargar lazy content
                await page.evaluate("""async () => {
                    await new Promise(r => {
                        let h = 0; const d = 100;
                        const t = setInterval(() => {
                            window.scrollBy(0, d); h += d;
                            if (h >= document.body.scrollHeight) { clearInterval(t); r(); }
                        }, 50);
                    });
                }""")
                await page.wait_for_timeout(1000)

                enlaces = await page.query_selector_all('a[href*="/propiedad/"]')
                for enlace in enlaces:
                    href = await enlace.get_attribute('href')
                    if href and '/propiedad/' in href:
                        if href.startswith('/'):
                            urls.add(f"https://{config['domain']}{href}")
                        elif href.startswith('http'):
                            urls.add(href)
        finally:
            await browser.close()

    return sorted(urls)


async def _extraer_urls_lamudi(config: dict) -> List[str]:
    """Extractor de URLs específico para Lamudi Mazatlán"""
    urls = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='es-MX',
            timezone_id='America/Mexico_City'
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        page = await context.new_page()

        try:
            base_url = config['listado_url']
            num_pagina = 1

            while True:
                page_url = base_url if num_pagina == 1 else f"{base_url}?page={num_pagina}"
                print(f"📄 Lamudi - Página {num_pagina}: {page_url}")

                await page.goto(page_url, wait_until='networkidle', timeout=60000)
                await page.wait_for_timeout(3000)

                # Scroll para cargar contenido lazy
                await page.evaluate("""async () => {
                    await new Promise(r => {
                        let h = 0; const d = 200;
                        const t = setInterval(() => {
                            window.scrollBy(0, d); h += d;
                            if (h >= document.body.scrollHeight) { clearInterval(t); r(); }
                        }, 80);
                    });
                }""")
                await page.wait_for_timeout(1500)

                # Extraer links a /detalle/
                enlaces = await page.query_selector_all('a[href*="/detalle/"]')
                nuevas = 0
                for enlace in enlaces:
                    href = await enlace.get_attribute('href')
                    if href and '/detalle/' in href:
                        full_url = href if href.startswith('http') else f"https://{config['domain']}{href}"
                        if full_url not in urls:
                            urls.add(full_url)
                            nuevas += 1

                print(f"   → {nuevas} nuevas URLs (total: {len(urls)})")

                # Si la página no aportó URLs nuevas, llegamos al final del listado.
                # (Antes se usaba un selector de "botón siguiente" que Lamudi ya cambió;
                #  apoyarse en "0 nuevas" es más robusto.)
                if nuevas == 0:
                    print("   → Sin nuevas propiedades, fin de la paginación")
                    break

                # Tope de seguridad para no quedar en bucle infinito
                if num_pagina >= 80:
                    print("   → Tope de seguridad de 80 páginas alcanzado")
                    break

                num_pagina += 1

                # Delay entre páginas para no saturar
                await page.wait_for_timeout(2000)

        finally:
            await browser.close()

    return sorted(urls)


# ========================================
# ENDPOINTS
# ========================================

@app.get("/")
async def root():
    return {
        "message": "API Scraper de Propiedades - TIBESA v4",
        "version": "3.0.0",
        "sitios_soportados": list(SCRAPERS_MAP.keys()),
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/api/scrape/stream/{site_id}")
async def scrape_stream(site_id: str, request: Request, zona: Optional[int] = None):
    """
    Endpoint SSE: Scrapea todas las propiedades de un sitio y transmite
    cada resultado en tiempo real al frontend.

    Query params:
    - zona: (solo RE/MAX) ID de zona 1-8. Si se omite, scrapea las 8 zonas.

    Eventos enviados:
    - phase: fase actual (extracting_urls, scraping)
    - progress: progreso general {current, total, percent}
    - property: datos de una propiedad scrapeada
    - done: scraping completado con estadísticas
    - error: si algo falla
    """
    if site_id not in SCRAPERS_MAP:
        raise HTTPException(status_code=404, detail=f"Sitio '{site_id}' no encontrado")

    config = SCRAPERS_MAP[site_id]

    if config.get('is_remax'):
        zona_ids = [zona] if zona else list(RemaxSunsetEagleScraper.ZONAS.keys())
        if zona and zona not in RemaxSunsetEagleScraper.ZONAS:
            raise HTTPException(status_code=400, detail=f"Zona {zona} inválida. Válidas: 1-8")
        return EventSourceResponse(_event_generator_remax(site_id, config, zona_ids, request))

    # Mitula usa un flujo diferente: scrapea directo del listado
    if config.get('scrape_from_listing'):
        return EventSourceResponse(_event_generator_listing(site_id, config, request))
    else:
        return EventSourceResponse(_event_generator_detail(site_id, config, request))


async def _event_generator_remax(site_id: str, config: dict, zona_ids: List[int], request: Request):
    """Generador SSE para RE/MAX Sunset Eagle: discovery por zona(s) + detalle por propiedad."""
    scraper = RemaxSunsetEagleScraper(
        output_dir="data",
        descargar_imagenes=True,
        max_imagenes_por_propiedad=1,
    )

    zonas_label = (
        f"zona {scraper.ZONAS[zona_ids[0]]}"
        if len(zona_ids) == 1
        else f"{len(zona_ids)} zonas"
    )

    yield {
        "event": "phase",
        "data": json.dumps({
            "phase": "extracting_urls",
            "message": f"Buscando propiedades en {config['name']} ({zonas_label})...",
        }),
    }

    all_targets: List[tuple] = []  # [(url, zona_nombre)]
    try:
        async with aiohttp.ClientSession(headers=scraper.DEFAULT_HEADERS) as session:
            for zid in zona_ids:
                if await request.is_disconnected():
                    return
                urls, _ = await scraper.discover_urls_por_zona(session, zid)
                zona_nombre = scraper.ZONAS[zid]
                all_targets.extend([(u, zona_nombre) for u in urls])
    except Exception as e:
        yield {"event": "error", "data": json.dumps({"message": f"Error en discovery: {str(e)}"})}
        return

    total = len(all_targets)
    if total == 0:
        yield {"event": "error", "data": json.dumps({"message": "No se encontraron propiedades en las zonas solicitadas"})}
        return

    yield {
        "event": "phase",
        "data": json.dumps({
            "phase": "scraping",
            "message": f"Scrapeando {total} propiedades de {config['name']}...",
            "total": total,
        }),
    }

    exitosas = 0
    fallidas = 0
    propiedades_guardar = []
    inicio = time.monotonic()
    iniciado_iso = datetime.utcnow().isoformat()

    async with aiohttp.ClientSession(headers=scraper.DEFAULT_HEADERS) as session:
        for idx, (url, zona_nombre) in enumerate(all_targets, 1):
            if await request.is_disconnected():
                break

            percent = round((idx / total) * 100) if total > 0 else 0
            yield {
                "event": "progress",
                "data": json.dumps({"current": idx, "total": total, "percent": percent, "url": url}),
            }

            try:
                prop = await scraper.extraer_detalle(session, url, zona_nombre)
                if not prop:
                    raise RuntimeError("extraer_detalle devolvió None")

                exitosas += 1
                propiedades_guardar.append(prop)
                resumen = {
                    "index": idx,
                    "total": total,
                    "titulo": prop.get("titulo") or "Sin título",
                    "precio": prop.get("precio") or "N/A",
                    "ubicacion": prop.get("ubicacion") or "N/A",
                    "tipo_propiedad": prop.get("tipo_propiedad") or "N/A",
                    "zona": prop.get("zona"),
                    "descripcion_comercial": "",
                    "destacados_venta": prop.get("amenidades", [])[:5],
                    "num_imagenes": len(prop.get("imagenes_descargadas", [])),
                    "url": prop.get("url", ""),
                    "procesado_con_ia": False,
                    "terreno": prop.get("terreno", {}),
                    "construccion": {},
                    "espacios_interiores": prop.get("caracteristicas", {}),
                }
                yield {"event": "property", "data": json.dumps(resumen, ensure_ascii=False)}

            except Exception as e:
                fallidas += 1
                yield {
                    "event": "property_error",
                    "data": json.dumps({"index": idx, "url": url, "error": str(e)}),
                }

    # Persistir en Supabase (UPSERT por fuente, property_id) + registrar duración
    await asyncio.to_thread(upsert_propiedades, site_id, propiedades_guardar)
    duracion = time.monotonic() - inicio
    await asyncio.to_thread(registrar_scrapeo, site_id, exitosas, duracion, iniciado_iso, datetime.utcnow().isoformat())

    yield {
        "event": "done",
        "data": json.dumps({
            "total": total,
            "exitosas": exitosas,
            "con_ia": 0,
            "fallidas": fallidas,
            "duracion_segundos": round(duracion, 1),
        }),
    }


async def _event_generator_listing(site_id: str, config: dict, request: Request):
    """Generador SSE para scrapers que extraen datos del listado (Mitula)"""
    yield {
        "event": "phase",
        "data": json.dumps({"phase": "scraping", "message": f"Scrapeando propiedades de {config['name']}..."})
    }

    scraper = config['class'](output_dir="data")
    exitosas = 0
    idx = 0
    inicio = time.monotonic()
    iniciado_iso = datetime.utcnow().isoformat()

    try:
        propiedades = await scraper.extraer_todas_las_propiedades()
    except Exception as e:
        yield {"event": "error", "data": json.dumps({"message": f"Error en scraping: {str(e)}"})}
        return

    total = len(propiedades)

    for prop in propiedades:
        if await request.is_disconnected():
            return

        idx += 1
        exitosas += 1
        percent = round((idx / total) * 100) if total > 0 else 0

        yield {
            "event": "progress",
            "data": json.dumps({"current": idx, "total": total, "percent": percent, "url": ""})
        }

        resumen = {
            "index": idx,
            "total": total,
            "titulo": prop.get('titulo', 'Sin título'),
            "precio": prop.get('precio', 'N/A'),
            "ubicacion": prop.get('ubicacion', 'N/A'),
            "tipo_propiedad": prop.get('tipo_propiedad', 'N/A'),
            "descripcion_comercial": "",
            "destacados_venta": [],
            "num_imagenes": len(prop.get('imagenes_descargadas', [])),
            "url": prop.get('url', ''),
            "procesado_con_ia": False,
            "terreno": prop.get('terreno', {}),
            "construccion": {},
            "espacios_interiores": {},
        }

        yield {"event": "property", "data": json.dumps(resumen, ensure_ascii=False)}

    # Persistir en Supabase (UPSERT por fuente, property_id) + registrar duración
    await asyncio.to_thread(upsert_propiedades, site_id, propiedades)
    duracion = time.monotonic() - inicio
    await asyncio.to_thread(registrar_scrapeo, site_id, exitosas, duracion, iniciado_iso, datetime.utcnow().isoformat())

    yield {
        "event": "done",
        "data": json.dumps({
            "total": total,
            "exitosas": exitosas,
            "con_ia": 0,
            "fallidas": 0,
            "duracion_segundos": round(duracion, 1),
        })
    }


# Cada cuántas propiedades se vuelca el avance a Supabase (para no perder progreso)
FLUSH_CADA = 25

# Fallos seguidos que disparan el "cortacircuitos" (probable bloqueo del sitio)
UMBRAL_BLOQUEO = 8


def _es_error_de_cuota(data: dict) -> bool:
    """Detecta si el LLM falló por falta de crédito/cuota de OpenAI."""
    analisis = data.get('analisis_llm')
    err = str(analisis.get('error', '')).lower() if isinstance(analisis, dict) else ''
    return any(k in err for k in (
        'insufficient_quota', 'exceeded your current quota', 'quota', 'billing',
        'insufficient funds', 'payment',
    ))


def _extraccion_vacia(data: dict) -> bool:
    """True si la página no devolvió datos clave (señal de página bloqueada/captcha)."""
    return not (data.get('titulo') or data.get('precio'))


# Títulos típicos de páginas de bloqueo/captcha (Lamudi, Cloudflare, etc.)
_TITULOS_BLOQUEO = (
    'confirme que es humano', 'are you human', 'verifying you are human',
    'just a moment', 'attention required', 'access denied', 'acceso denegado',
    'captcha', 'robot', 'verificación', 'verificacion', 'one more step',
)


def _pagina_bloqueada(data: dict) -> bool:
    """True si el contenido indica una página de captcha/bloqueo (aunque traiga título)."""
    titulo = str(data.get('titulo') or '').lower()
    return any(k in titulo for k in _TITULOS_BLOQUEO)


def _pagina_invalida(data: dict) -> bool:
    """Página sin datos útiles: vacía o bloqueada (no debe guardarse)."""
    return _extraccion_vacia(data) or _pagina_bloqueada(data)


async def _event_generator_detail(site_id: str, config: dict, request: Request):
    """Generador SSE para scrapers que navegan a cada propiedad (Paraíso Dorado, Lamudi).

    Optimizado: un solo navegador compartido + N propiedades en paralelo (semáforo).
    No descarga imágenes (el cliente solo consulta/conversa con la IA sobre texto).
    """
    inicio = time.monotonic()
    iniciado_iso = datetime.utcnow().isoformat()

    # Fase 1: Extraer URLs
    yield {
        "event": "phase",
        "data": json.dumps({"phase": "extracting_urls", "message": f"Buscando propiedades en {config['name']}..."})
    }

    try:
        urls = await extraer_urls_del_listado(site_id)
    except Exception as e:
        yield {"event": "error", "data": json.dumps({"message": f"Error extrayendo URLs: {str(e)}"})}
        return

    total = len(urls)
    yield {
        "event": "phase",
        "data": json.dumps({"phase": "scraping", "message": f"Scrapeando {total} propiedades...", "total": total})
    }

    # Fase 2: Scrapear en paralelo (sin imágenes)
    scraper = config['class'](output_dir="data", descargar_imagenes=False)
    exitosas = 0
    con_ia = 0
    guardadas_total = 0          # cuántas se han volcado a Supabase
    buffer = []                  # propiedades pendientes de volcar
    sin_credito = False          # se agotó el crédito de OpenAI
    posible_bloqueo = False      # el sitio parece estar bloqueándonos
    fallos_seguidos = 0          # contador para el cortacircuitos

    async def _flush():
        """Vuelca el buffer a Supabase y lo limpia (guardado incremental)."""
        nonlocal buffer, guardadas_total
        if buffer:
            await asyncio.to_thread(upsert_propiedades, site_id, buffer)
            guardadas_total += len(buffer)
            buffer = []

    sem = asyncio.Semaphore(CONCURRENCIA_DETALLE)
    cola: asyncio.Queue = asyncio.Queue()

    async def _procesar(idx: int, url: str, context):
        """Worker: scrapea una propiedad + LLM, y deja el resultado en la cola."""
        async with sem:
            # Pausa aleatoria para escalonar las peticiones (anti-bloqueo)
            await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
            try:
                data = await scraper.extraer_con_contexto(context, url)
                ia = False
                if data.get('descripcion'):
                    try:
                        # El LLM es síncrono (red): lo corremos en un hilo para no
                        # bloquear el event loop y permitir las llamadas en paralelo.
                        data = await asyncio.to_thread(procesar_propiedad_con_llm, data)
                        analisis = data.get('analisis_llm') or {}
                        ia = isinstance(analisis, dict) and bool(analisis) and 'error' not in analisis
                    except Exception:
                        pass
                await cola.put((idx, url, data, ia, None))
            except Exception as e:
                await cola.put((idx, url, None, False, str(e)))

    async with async_playwright() as p:
        browser = await p.chromium.launch(**scraper.get_browser_config())
        context = await browser.new_context(**scraper.get_context_config())
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )

        tasks = [asyncio.create_task(_procesar(i, u, context)) for i, u in enumerate(urls, 1)]

        try:
            for completado in range(1, total + 1):
                if await request.is_disconnected():
                    break

                idx, url, data, ia, err = await cola.get()

                yield {
                    "event": "progress",
                    "data": json.dumps({
                        "current": completado, "total": total,
                        "percent": round(completado / total * 100) if total else 0, "url": url,
                    })
                }

                # Fallo de scraping (timeout/error) o página inválida (vacía o captcha/bloqueo)
                if err or not data or _pagina_invalida(data):
                    fallos_seguidos += 1
                    motivo_fallo = err or ("captcha/bloqueo" if data and _pagina_bloqueada(data) else "página sin datos")
                    yield {
                        "event": "property_error",
                        "data": json.dumps({"index": idx, "total": total, "url": url, "error": motivo_fallo})
                    }
                    # Cortacircuitos: demasiados fallos seguidos → probable bloqueo del sitio
                    if fallos_seguidos >= UMBRAL_BLOQUEO:
                        posible_bloqueo = True
                        yield {
                            "event": "warning",
                            "data": json.dumps({
                                "message": f"{fallos_seguidos} fallos seguidos: el sitio podría estar bloqueándonos. "
                                           "Finalizando y guardando lo avanzado hasta aquí."
                            })
                        }
                        break
                    continue

                fallos_seguidos = 0  # hubo éxito → reiniciar el contador

                # Se acabó el crédito de OpenAI → finalizar limpio guardando lo avanzado
                if _es_error_de_cuota(data):
                    sin_credito = True
                    yield {
                        "event": "warning",
                        "data": json.dumps({
                            "message": "Se agotó el crédito/cuota de OpenAI. Finalizando y guardando lo avanzado hasta aquí."
                        })
                    }
                    break

                exitosas += 1
                if ia:
                    con_ia += 1
                buffer.append(data)

                # Guardado incremental: cada FLUSH_CADA propiedades se vuelcan a Supabase
                if len(buffer) >= FLUSH_CADA:
                    await _flush()

                # Guardar JSON local
                prop_id = data.get('property_id', idx)
                json_path = JSON_DIR / f"{site_id}_{prop_id}.json"
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                analisis = data.get('analisis_llm', {}) if isinstance(data.get('analisis_llm'), dict) else {}
                resumen = {
                    "index": idx,
                    "total": total,
                    "titulo": data.get('titulo', 'Sin título'),
                    "precio": data.get('precio', 'N/A'),
                    "ubicacion": data.get('ubicacion', 'N/A'),
                    "tipo_propiedad": data.get('tipo_propiedad') or analisis.get('tipo_propiedad', 'N/A'),
                    "descripcion_comercial": analisis.get('descripcion_comercial', ''),
                    "destacados_venta": analisis.get('destacados_venta', []),
                    "num_imagenes": len(data.get('imagenes_descargadas', [])),
                    "url": url,
                    "procesado_con_ia": data.get('procesado_con_llm', False),
                    "terreno": analisis.get('terreno', {}),
                    "construccion": analisis.get('construccion', {}),
                    "espacios_interiores": analisis.get('espacios_interiores', {}),
                }
                yield {"event": "property", "data": json.dumps(resumen, ensure_ascii=False)}
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()
            await browser.close()

    # Volcar el remanente del buffer (guardado incremental) + registrar duración
    await _flush()
    duracion = time.monotonic() - inicio
    await asyncio.to_thread(registrar_scrapeo, site_id, guardadas_total, duracion, iniciado_iso, datetime.utcnow().isoformat())

    # Completado (motivo: completado normal o corte por falta de crédito)
    yield {
        "event": "done",
        "data": json.dumps({
            "total": total,
            "exitosas": exitosas,
            "con_ia": con_ia,
            "fallidas": total - exitosas,
            "guardadas": guardadas_total,
            "duracion_segundos": round(duracion, 1),
            "motivo": (
                "sin_credito_openai" if sin_credito
                else "posible_bloqueo" if posible_bloqueo
                else "completado"
            ),
        })
    }


@app.get("/api/properties")
async def list_properties():
    """Lista todas las propiedades scrapeadas"""
    json_files = list(JSON_DIR.glob("*.json"))
    propiedades = []

    for json_file in sorted(json_files, reverse=True):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                analisis = data.get('analisis_llm', {})
                propiedades.append({
                    "id": json_file.stem,
                    "titulo": data.get("titulo"),
                    "ubicacion": data.get("ubicacion"),
                    "precio": data.get("precio"),
                    "tipo_propiedad": data.get("tipo_propiedad") or analisis.get("tipo_propiedad"),
                    "descripcion_comercial": analisis.get("descripcion_comercial", ""),
                    "destacados_venta": analisis.get("destacados_venta", []),
                    "url": data.get("url"),
                    "num_imagenes": len(data.get("imagenes_descargadas", [])),
                    "procesado_con_ia": data.get("procesado_con_llm", False),
                })
        except Exception:
            continue

    return {"success": True, "count": len(propiedades), "properties": propiedades}


@app.get("/api/propiedades/estado")
async def propiedades_estado():
    """
    Frescura de los datos guardados por portal: total de propiedades y fecha de
    última actualización. El frontend lo usa para mostrar "actualizado hace X días"
    y ofrecer consultar lo guardado en vez de volver a scrapear.
    """
    estado = await asyncio.to_thread(estado_propiedades)
    return {"success": True, "estado": estado}


@app.get("/api/propiedades")
async def propiedades_guardadas(fuente: Optional[str] = None, limit: int = 500):
    """
    Devuelve las propiedades ya guardadas en Supabase (sin scrapear), en el mismo
    formato de tarjeta que emite el scraping en vivo.
    Filtra por portal con ?fuente=paraiso_dorado|lamudi|mitula|remax_sunset_eagle.
    """
    payloads = await asyncio.to_thread(obtener_propiedades, fuente, limit)
    propiedades = [_resumen_card(p, i) for i, p in enumerate(payloads, 1)]
    return {"success": True, "count": len(propiedades), "properties": propiedades}


# ========================================
# CHAT CON IA SOBRE PROPIEDADES SCRAPEADAS
# ========================================

def _resumen_card(data: dict, index: int = 0) -> dict:
    """Convierte el payload completo de una propiedad al formato que renderiza PropertyCard
    (el mismo que emiten los eventos SSE 'property'). Se usa para mostrar datos guardados."""
    analisis = data.get('analisis_llm', {}) if isinstance(data.get('analisis_llm'), dict) else {}
    imagenes = data.get('imagenes_descargadas') or data.get('imagenes') or []
    return {
        "index": index,
        "titulo": data.get('titulo', 'Sin título'),
        "precio": data.get('precio', 'N/A'),
        "ubicacion": data.get('ubicacion', 'N/A'),
        "tipo_propiedad": data.get('tipo_propiedad') or analisis.get('tipo_propiedad', 'N/A'),
        "descripcion_comercial": analisis.get('descripcion_comercial', ''),
        "destacados_venta": analisis.get('destacados_venta', []),
        "num_imagenes": len(imagenes) if isinstance(imagenes, list) else 0,
        "url": data.get('url', ''),
        "procesado_con_ia": data.get('procesado_con_llm', bool(analisis)),
        "terreno": analisis.get('terreno', {}) or data.get('terreno', {}),
        "construccion": analisis.get('construccion', {}),
        "espacios_interiores": analisis.get('espacios_interiores', {}) or data.get('caracteristicas', {}),
    }


def _resumen_para_chat(data: dict) -> dict:
    """Reduce el payload completo de una propiedad a los campos que usa el chat."""
    analisis = data.get('analisis_llm', {}) if isinstance(data.get('analisis_llm'), dict) else {}
    return {
        "titulo": data.get("titulo"),
        "precio": data.get("precio"),
        "ubicacion": data.get("ubicacion"),
        "tipo_propiedad": data.get("tipo_propiedad") or analisis.get("tipo_propiedad"),
        "descripcion_comercial": analisis.get("descripcion_comercial", ""),
        "terreno": analisis.get("terreno", {}) or data.get("terreno", {}),
        "construccion": analisis.get("construccion", {}),
        "espacios_interiores": analisis.get("espacios_interiores", {}) or data.get("caracteristicas", {}),
    }


class ChatRequest(BaseModel):
    message: str
    properties: Optional[List[dict]] = None  # Propiedades del frontend (en memoria)
    fuente: Optional[str] = None  # Filtrar por portal al leer de Supabase (opcional)


@app.post("/api/chat")
async def chat_propiedades(req: ChatRequest):
    """
    Chat con IA que responde preguntas basándose en las propiedades scrapeadas.
    El frontend envía las propiedades en memoria para que la IA las use como contexto.
    """
    api_key = os.getenv('OPENAI_API_KEY')
    model_name = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')

    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY no configurada")

    # Fuentes de datos para el chat, en orden de prioridad:
    #   1) Propiedades que el frontend ya tiene en memoria (req.properties)
    #   2) Supabase (datos persistidos: el cliente consulta SIN volver a scrapear)
    #   3) Disco local (fallback)
    propiedades = req.properties

    if not propiedades:
        payloads = await asyncio.to_thread(obtener_propiedades, req.fuente)
        propiedades = [_resumen_para_chat(p) for p in payloads]

    if not propiedades:
        json_files = list(JSON_DIR.glob("*.json"))
        for jf in sorted(json_files, reverse=True)[:100]:
            try:
                with open(jf, 'r', encoding='utf-8') as f:
                    propiedades.append(_resumen_para_chat(json.load(f)))
            except Exception:
                continue

    if not propiedades:
        return {"response": "No hay propiedades scrapeadas aún. Ejecuta un scraping primero."}

    # Construir contexto con los datos
    props_text = json.dumps(propiedades, ensure_ascii=False, indent=1)

    llm = init_chat_model(model_name, model_provider="openai", api_key=api_key, temperature=0.3)

    system = f"""Eres un asistente experto en bienes raíces de Mazatlán, Sinaloa, México.
Tienes acceso a los datos de {len(propiedades)} propiedades scrapeadas de sitios inmobiliarios.

DATOS DE PROPIEDADES DISPONIBLES:
{props_text}

INSTRUCCIONES:
- Responde SIEMPRE en español
- Basa tus respuestas EXCLUSIVAMENTE en los datos proporcionados
- Si preguntan por precios promedio, calcula basándote en los datos reales
- Si preguntan por una zona específica, filtra las propiedades de esa zona
- Si no hay datos suficientes para responder, dilo honestamente
- Sé conciso pero informativo
- Usa formato con viñetas cuando listes propiedades
- Incluye precios y ubicaciones cuando sea relevante"""

    try:
        response = llm.invoke([
            SystemMessage(content=system),
            HumanMessage(content=req.message)
        ])
        return {"response": response.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error del LLM: {str(e)}")


# ========================================
# BROCHURE INMOBILIARIO TIBESA
# ========================================

BROCHURES_DIR = DATA_DIR / "brochures"
BROCHURES_DIR.mkdir(parents=True, exist_ok=True)


@app.post("/api/brochure/generate")
async def generate_brochure():
    """
    Genera un brochure inmobiliario PDF con el análisis completo
    de las propiedades scrapeadas (medias por zona, comparables,
    escenarios de inversión). Retorna metadata con nombre de archivo
    para descarga posterior.
    """
    try:
        pdf_path = await generar_brochure(
            json_dir=JSON_DIR,
            output_dir=BROCHURES_DIR,
        )
        return {
            "success": True,
            "filename": pdf_path.name,
            "size_bytes": pdf_path.stat().st_size,
            "download_url": f"/api/brochure/download/{pdf_path.name}",
            "generated_at": datetime.now().isoformat(),
        }
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando brochure: {str(e)}")


@app.get("/api/brochure/download/{filename}")
async def download_brochure(filename: str):
    """Descarga un brochure PDF generado previamente."""
    # Seguridad: evitar path traversal
    if "/" in filename or ".." in filename or not filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Nombre de archivo inválido")

    pdf_path = BROCHURES_DIR / filename
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Brochure no encontrado")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=filename,
    )


@app.get("/api/brochure/list")
async def list_brochures():
    """Lista todos los brochures generados."""
    brochures = []
    for pdf in sorted(BROCHURES_DIR.glob("*.pdf"), reverse=True):
        stat = pdf.stat()
        brochures.append({
            "filename": pdf.name,
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "download_url": f"/api/brochure/download/{pdf.name}",
        })
    return {"success": True, "count": len(brochures), "brochures": brochures}


# ========================================
# EJECUTAR SERVIDOR
# ========================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")

