"""
Scraper para KW México / Keller Williams (https://www.kwmexico.mx)

SPA Angular en S3/CloudFront (las rutas profundas dan 403; el sitio sirve un
prerender a bots). Los datos vienen de una API pública AWS API Gateway. NO hay
un endpoint limpio de "terrenos en Mazatlán": la búsqueda del SPA es geo/mapa
alrededor de puntos de interés. PERO el endpoint `Random_Properties_Info` acepta
un array de IDs y devuelve la ficha completa de cada propiedad, y los IDs son
enteros pequeños (~1..6500). Por eso se enumeran TODOS los IDs por lotes (HTTP
puro, sin navegador) y se filtran los de Mazatlán + tipo terreno.

- Property_Type_ID == 5  → terreno (confirmado por títulos "TERRENO EN VENTA...")
- Property_Operation_ID == 2 → venta
- ~38 terrenos en venta en Mazatlán.
"""

import asyncio
import json
import re
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

API = ("https://cuj9iqvhg9.execute-api.us-east-2.amazonaws.com/"
       "Produccion/Properties_API/Random_Properties_Info")
DETALLE_BASE = "https://www.kwmexico.mx/listingDetails"

MAX_ID = 6600          # techo de IDs (>7000 devuelve 0)
BATCH = 150            # IDs por petición
CONCURRENCIA = 8       # peticiones en paralelo
TERRENO_TYPE_ID = 5
VENTA_OPERATION_ID = 2

from utils.data_normalizer import DataNormalizer


class KWMexicoScraper:
    """Scraper de listado (API pública por enumeración de IDs) para KW México."""

    LISTADO_URL = "https://www.kwmexico.mx/"

    DEFAULT_HEADERS = {
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": "https://www.kwmexico.mx",
        "Referer": "https://www.kwmexico.mx/",
    }

    def __init__(self, output_dir: str = "data", headless: bool = True):
        self.output_dir = Path(output_dir)
        self.json_dir = self.output_dir / "json"
        self.images_dir = self.output_dir / "imagenes"
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.site_name = "kwmexico"
        self.normalizer = DataNormalizer()

    # ---------- API pública (consumida por _event_generator_listing) ----------

    async def extraer_todas_las_propiedades(self, callback=None, max_pages: int = 0) -> List[Dict[str, Any]]:
        lotes = [list(range(s, min(s + BATCH, MAX_ID + 1))) for s in range(1, MAX_ID + 1, BATCH)]
        sem = asyncio.Semaphore(CONCURRENCIA)

        async with aiohttp.ClientSession(headers=self.DEFAULT_HEADERS) as session:
            async def _pedir(ids: List[int]) -> List[Dict[str, Any]]:
                async with sem:
                    try:
                        async with session.post(API, json={"ArrayNumeros": ids},
                                                timeout=aiohttp.ClientTimeout(total=40)) as r:
                            if r.status != 200:
                                return []
                            data = await r.json(content_type=None)
                            return data.get("data", []) if isinstance(data, dict) else []
                    except Exception:
                        return []

            resultados = await asyncio.gather(*[_pedir(l) for l in lotes])

        # Filtrar Mazatlán + terreno en venta
        crudas = []
        for grupo in resultados:
            for p in grupo:
                if (p.get("Property_Type_ID") == TERRENO_TYPE_ID
                        and p.get("Property_Operation_ID") == VENTA_OPERATION_ID
                        and "mazatl" in (p.get("City") or "").lower()):
                    crudas.append(p)

        propiedades = [self._mapear(p) for p in crudas]
        propiedades = [p for p in propiedades if p]

        for prop in propiedades:
            try:
                with open(self.json_dir / f"{self.site_name}_{prop['property_id']}.json", "w", encoding="utf-8") as f:
                    json.dump(prop, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

        return propiedades

    def _mapear(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            pid = raw.get("ID")
            if not pid:
                return None

            mls = raw.get("MLS_Number")
            url = f"{DETALLE_BASE}/{mls}?lan=es-MX" if mls else f"{DETALLE_BASE}/{pid}?lan=es-MX"

            # Ubicación
            partes = [raw.get("Colony") or raw.get("Geo_Colonia"),
                      raw.get("City"), raw.get("State")]
            ubicacion = ", ".join(p for p in partes if p) or "Mazatlán, Sinaloa"

            # Precio
            moneda = raw.get("Currency") or "MXN"
            precio = None
            cp = raw.get("Current_Price")
            if cp:
                try:
                    precio = f"${int(float(cp)):,} {moneda}"
                except (ValueError, TypeError):
                    precio = f"{cp} {moneda}"

            # Título (algunos vienen vacíos → respaldo)
            titulo = (raw.get("Title") or "").strip()
            if not titulo:
                lugar = raw.get("Colony") or raw.get("City") or "Mazatlán"
                titulo = f"Terreno en venta en {lugar}"

            # Descripción (puede traer HTML)
            descripcion = None
            desc = raw.get("Description")
            if isinstance(desc, str) and desc.strip():
                txt = unescape(re.sub(r"<[^>]+>", " ", desc))
                descripcion = re.sub(r"\s+", " ", txt).strip() or None

            coords = {}
            if raw.get("Latitude") and raw.get("Longitude"):
                coords = {"lat": raw["Latitude"], "lng": raw["Longitude"]}

            imagenes = [raw["Photo_URL"]] if raw.get("Photo_URL") else []

            return {
                "url": url,
                "site": self.site_name,
                "property_id": str(pid),
                "empresa": "Keller Williams México",
                "titulo": titulo,
                "ubicacion": ubicacion,
                "precio": precio,
                "precio_normalizado": self.normalizer.normalizar_precio(precio) if precio else None,
                "moneda": moneda,
                "estado": "En venta",
                "tipo_propiedad": "terreno",
                "terreno": {},
                "caracteristicas": {},
                "descripcion": descripcion,
                "agente": {},
                "coordenadas": coords,
                "mls_number": mls,
                "imagenes": imagenes,
                "imagenes_descargadas": [],
            }
        except Exception:
            return None


async def main():
    scraper = KWMexicoScraper(output_dir="data")
    props = await scraper.extraer_todas_las_propiedades()
    print(f"\n✅ {len(props)} terrenos en venta en Mazatlán (KW México)")
    print(f"sin precio: {len([p for p in props if not p['precio']])} | con desc: {len([p for p in props if p.get('descripcion')])} | con coords: {len([p for p in props if p.get('coordenadas')])}")
    for p in props[:4]:
        print(f"  [{p['property_id']}] {(p['titulo'] or '')[:42]} | {p['precio']} | {p['url'][-30:]}")


if __name__ == "__main__":
    asyncio.run(main())
