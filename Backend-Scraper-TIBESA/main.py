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
from utils.agente_propiedades import procesar_propiedad_con_llm
from playwright.async_api import async_playwright

# Brochure generator
from brochure.generator import generar_brochure

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
}

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directorios
DATA_DIR = Path("data")
JSON_DIR = DATA_DIR / "json"
IMAGES_DIR = DATA_DIR / "imagenes"

JSON_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)


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

                # Si no encontramos nuevas URLs, terminamos
                if nuevas == 0:
                    print("   → Sin nuevas propiedades, fin de la paginación")
                    break

                # Verificar si hay página siguiente
                next_btn = await page.query_selector(
                    'a[rel="next"], [class*="pagination"] a:has-text(">")'
                )
                if not next_btn:
                    print("   → No hay botón siguiente, fin de la paginación")
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
        "message": "API Scraper de Propiedades - TIBESA",
        "version": "3.0.0",
        "sitios_soportados": list(SCRAPERS_MAP.keys()),
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/api/scrape/stream/{site_id}")
async def scrape_stream(site_id: str, request: Request):
    """
    Endpoint SSE: Scrapea todas las propiedades de un sitio y transmite
    cada resultado en tiempo real al frontend.

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

    # Mitula usa un flujo diferente: scrapea directo del listado
    if config.get('scrape_from_listing'):
        return EventSourceResponse(_event_generator_listing(site_id, config, request))
    else:
        return EventSourceResponse(_event_generator_detail(site_id, config, request))


async def _event_generator_listing(site_id: str, config: dict, request: Request):
    """Generador SSE para scrapers que extraen datos del listado (Mitula)"""
    yield {
        "event": "phase",
        "data": json.dumps({"phase": "scraping", "message": f"Scrapeando propiedades de {config['name']}..."})
    }

    scraper = config['class'](output_dir="data")
    exitosas = 0
    idx = 0

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

    yield {
        "event": "done",
        "data": json.dumps({
            "total": total,
            "exitosas": exitosas,
            "con_ia": 0,
            "fallidas": 0,
        })
    }


async def _event_generator_detail(site_id: str, config: dict, request: Request):
    """Generador SSE para scrapers que navegan a cada propiedad (Paraíso Dorado, Lamudi)"""
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

    # Fase 2: Scrapear cada propiedad
    scraper = config['class'](output_dir="data")
    exitosas = 0
    con_ia = 0

    for idx, url in enumerate(urls, 1):
        if await request.is_disconnected():
            return

        percent = round((idx / total) * 100)
        yield {
            "event": "progress",
            "data": json.dumps({"current": idx, "total": total, "percent": percent, "url": url})
        }

        try:
            resultado = await scraper.extraer_informacion(url)

            # Procesar con IA
            if resultado.get('descripcion'):
                try:
                    resultado = procesar_propiedad_con_llm(resultado)
                    con_ia += 1
                except Exception:
                    pass

            # Guardar JSON
            prop_id = resultado.get('property_id', idx)
            json_path = JSON_DIR / f"{site_id}_{prop_id}.json"
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(resultado, f, indent=2, ensure_ascii=False)

            exitosas += 1

            # Preparar resumen para el frontend
            analisis = resultado.get('analisis_llm', {})
            resumen = {
                "index": idx,
                "total": total,
                "titulo": resultado.get('titulo', 'Sin título'),
                "precio": resultado.get('precio', 'N/A'),
                "ubicacion": resultado.get('ubicacion', 'N/A'),
                "tipo_propiedad": resultado.get('tipo_propiedad') or analisis.get('tipo_propiedad', 'N/A'),
                "descripcion_comercial": analisis.get('descripcion_comercial', ''),
                "destacados_venta": analisis.get('destacados_venta', []),
                "num_imagenes": len(resultado.get('imagenes_descargadas', [])),
                "url": url,
                "procesado_con_ia": resultado.get('procesado_con_llm', False),
                "terreno": analisis.get('terreno', {}),
                "construccion": analisis.get('construccion', {}),
                "espacios_interiores": analisis.get('espacios_interiores', {}),
            }

            yield {"event": "property", "data": json.dumps(resumen, ensure_ascii=False)}

        except Exception as e:
            yield {
                "event": "property_error",
                "data": json.dumps({"index": idx, "total": total, "url": url, "error": str(e)})
            }

        # Delay entre requests
        await asyncio.sleep(1.5)

    # Completado
    yield {
        "event": "done",
        "data": json.dumps({
            "total": total,
            "exitosas": exitosas,
            "con_ia": con_ia,
            "fallidas": total - exitosas,
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


# ========================================
# CHAT CON IA SOBRE PROPIEDADES SCRAPEADAS
# ========================================

class ChatRequest(BaseModel):
    message: str
    properties: Optional[List[dict]] = None  # Propiedades del frontend (en memoria)


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

    # Usar propiedades enviadas desde el frontend o cargar del disco
    propiedades = req.properties
    if not propiedades:
        json_files = list(JSON_DIR.glob("*.json"))
        propiedades = []
        for jf in sorted(json_files, reverse=True)[:100]:
            try:
                with open(jf, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    analisis = data.get('analisis_llm', {})
                    propiedades.append({
                        "titulo": data.get("titulo"),
                        "precio": data.get("precio"),
                        "ubicacion": data.get("ubicacion"),
                        "tipo_propiedad": data.get("tipo_propiedad") or analisis.get("tipo_propiedad"),
                        "descripcion_comercial": analisis.get("descripcion_comercial", ""),
                        "terreno": analisis.get("terreno", {}),
                        "construccion": analisis.get("construccion", {}),
                        "espacios_interiores": analisis.get("espacios_interiores", {}),
                    })
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

