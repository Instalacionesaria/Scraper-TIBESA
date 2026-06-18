"""
Scraper para BuscaTuCasa (https://catalogo.buscatucasa.mx)

Inmobiliaria directa de Mazatlán. El catálogo es WordPress (tema RealHomes) con
la **REST API pública** habilitada, así que se scrapea con HTTP puro (aiohttp)
desde `/wp-json/wp/v2/properties` — datos estructurados, sin Playwright, sin
anti-bot (Cloudflare en modo pasivo).

- Filtro por tipo: `?property-types=62` (62 = "terreno"). 11 terrenos.
- Cada propiedad trae meta RealHomes: precio, superficie, ubicación (lat/lng),
  dirección, recámaras/baños, galería de imágenes, y la descripción en `content`.
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from utils.data_normalizer import DataNormalizer

BASE = "https://catalogo.buscatucasa.mx"
API = f"{BASE}/wp-json/wp/v2/properties"
TERRENO_TYPE_ID = 62  # taxonomía property-types slug "terreno"
UPLOADS = f"{BASE}/wp-content/uploads/"


class BuscaTuCasaScraper:
    """Scraper de listado (HTTP plano + WP REST API RealHomes) para BuscaTuCasa."""

    LISTADO_URL = f"{BASE}/blog/property-type/terreno/"

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
    }

    def __init__(self, output_dir: str = "data", headless: bool = True):
        self.output_dir = Path(output_dir)
        self.json_dir = self.output_dir / "json"
        self.images_dir = self.output_dir / "imagenes"
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.site_name = "buscatucasa"
        self.normalizer = DataNormalizer()

    # ---------- API pública (consumida por _event_generator_listing) ----------

    async def extraer_todas_las_propiedades(self, callback=None, max_pages: int = 0) -> List[Dict[str, Any]]:
        async with aiohttp.ClientSession(headers=self.DEFAULT_HEADERS) as session:
            crudas = await self._pedir_terrenos(session)
            propiedades = [self._mapear(p) for p in crudas]
            propiedades = [p for p in propiedades if p]

            for prop in propiedades:
                try:
                    with open(self.json_dir / f"{self.site_name}_{prop['property_id']}.json", "w", encoding="utf-8") as f:
                        json.dump(prop, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

            return propiedades

    async def _pedir_terrenos(self, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        """Pagina la REST API de propiedades filtrando por tipo terreno."""
        resultados: List[Dict[str, Any]] = []
        pagina = 1
        while pagina <= 20:
            url = f"{API}?property-types={TERRENO_TYPE_ID}&per_page=50&page={pagina}&_embed"
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=40)) as resp:
                    if resp.status != 200:
                        break
                    data = await resp.json(content_type=None)
            except Exception:
                break
            if not isinstance(data, list) or not data:
                break
            resultados.extend(data)
            if len(data) < 50:
                break
            pagina += 1
        return resultados

    def _mapear(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            pid = raw.get("id")
            if not pid:
                return None
            pm = raw.get("property_meta", {}) or {}

            titulo = (raw.get("title", {}) or {}).get("rendered") or None
            url = raw.get("link") or f"{BASE}/?p={pid}"

            # Precio
            precio = None
            moneda = "MXN"
            precio_raw = pm.get("REAL_HOMES_property_price")
            if precio_raw:
                try:
                    precio = f"${int(float(precio_raw)):,} {moneda}"
                except (ValueError, TypeError):
                    precio = str(precio_raw)

            # Superficie
            terreno: Dict[str, Any] = {}
            caracteristicas: Dict[str, Any] = {}
            size = pm.get("REAL_HOMES_property_size") or pm.get("REAL_HOMES_property_lot_size")
            if size:
                try:
                    val = float(str(size).strip())
                    terreno["superficie_m2"] = val
                    caracteristicas["superficie_m2"] = val
                except (ValueError, TypeError):
                    pass
            for campo, clave in (("REAL_HOMES_property_bedrooms", "recamaras"),
                                 ("REAL_HOMES_property_bathrooms", "baños"),
                                 ("REAL_HOMES_property_garage", "estacionamientos")):
                v = pm.get(campo)
                if v and str(v).strip() not in ("", "0"):
                    caracteristicas[clave] = v

            # Ubicación + coordenadas
            ubicacion = pm.get("REAL_HOMES_property_address") or "Mazatlán, Sinaloa"
            coords = {}
            loc = pm.get("REAL_HOMES_property_location")
            if isinstance(loc, dict) and loc.get("latitude"):
                coords = {"lat": loc.get("latitude"), "lng": loc.get("longitude")}

            # Descripción (content), limpiando HTML
            descripcion = None
            cont = (raw.get("content", {}) or {}).get("rendered", "")
            if cont:
                txt = re.sub(r"<[^>]+>", " ", cont)
                txt = re.sub(r"\s+", " ", txt).strip()
                descripcion = txt or None

            # Imágenes: galería REAL_HOMES_property_images (campo 'file') + featured
            imagenes: List[str] = []
            galeria = pm.get("REAL_HOMES_property_images")
            if isinstance(galeria, list):
                for img in galeria:
                    f = img.get("file") if isinstance(img, dict) else None
                    if f:
                        full = f"{UPLOADS}{f}"
                        if full not in imagenes:
                            imagenes.append(full)
            # featured (vía _embed) como respaldo / portada
            emb = raw.get("_embedded", {}) or {}
            fm = emb.get("wp:featuredmedia") or []
            if fm and isinstance(fm, list):
                src = fm[0].get("source_url")
                if src and src not in imagenes:
                    imagenes.insert(0, src)

            return {
                "url": url,
                "site": self.site_name,
                "property_id": str(pid),
                "empresa": "BuscaTuCasa",
                "titulo": titulo,
                "ubicacion": ubicacion,
                "precio": precio,
                "precio_normalizado": self.normalizer.normalizar_precio(precio) if precio else None,
                "moneda": moneda,
                "estado": "En venta",
                "tipo_propiedad": "terreno",
                "terreno": terreno,
                "caracteristicas": caracteristicas,
                "descripcion": descripcion,
                "agente": {},
                "coordenadas": coords,
                "imagenes": imagenes,
                "imagenes_descargadas": [],
            }
        except Exception:
            return None


async def main():
    scraper = BuscaTuCasaScraper(output_dir="data")
    props = await scraper.extraer_todas_las_propiedades()
    print(f"\n✅ {len(props)} propiedades extraídas")
    print(f"sin precio: {len([p for p in props if not p['precio']])} | con desc: {len([p for p in props if p.get('descripcion')])} | con img: {len([p for p in props if p.get('imagenes')])}")
    for p in props[:3]:
        print(f"  [{p['property_id']}] {(p['titulo'] or '')[:45]} | {p['precio']} | {p['terreno']} | imgs={len(p.get('imagenes',[]))}")


if __name__ == "__main__":
    asyncio.run(main())
