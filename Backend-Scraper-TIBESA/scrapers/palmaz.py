"""
Scraper para Palmaz Inmobiliaria (https://palmazinmobiliaria.com)

Inmobiliaria directa de Mazatlán, plataforma Wasi (Laravel + Vue). SIN anti-bot
(HTTP 200 plano). Se scrapea con HTTP puro (aiohttp), sin Playwright.

- El listado de terrenos en venta server-rendea las tarjetas con título, precio,
  ubicación, tipo, imagen y link `/{slug}/{id}`. ~12 terrenos, sin paginación
  (la categoría cabe en una página).
- La descripción rica y las coordenadas se toman del JSON-LD (@type house) de la
  ficha de detalle (el precio NO está en el JSON-LD → se toma de la tarjeta).
"""

import asyncio
import json
import re
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from utils.data_normalizer import DataNormalizer

BASE = "https://palmazinmobiliaria.com"
LISTADO_URL = f"{BASE}/s/terreno/ventas?id_property_type=32&business_type%5B0%5D=for_sale"
CONCURRENCIA_DETALLE = 6
_LD_RE = re.compile(r'application/ld\+json[^>]*>(.*?)</script>', re.S)


class PalmazScraper:
    """Scraper de listado (HTTP plano + Wasi) para Palmaz Inmobiliaria."""

    LISTADO_URL = LISTADO_URL

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
    }

    def __init__(self, output_dir: str = "data", headless: bool = True):
        self.output_dir = Path(output_dir)
        self.json_dir = self.output_dir / "json"
        self.images_dir = self.output_dir / "imagenes"
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.site_name = "palmaz"
        self.normalizer = DataNormalizer()

    # ---------- API pública (consumida por _event_generator_listing) ----------

    async def extraer_todas_las_propiedades(self, callback=None, max_pages: int = 0) -> List[Dict[str, Any]]:
        async with aiohttp.ClientSession(headers=self.DEFAULT_HEADERS) as session:
            html = await self._get(session, self.LISTADO_URL)
            if not html:
                return []
            propiedades = [self._mapear_card(b) for b in self._segmentar_cards(html)]
            propiedades = [p for p in propiedades if p]

            # dedup por property_id
            unicos: Dict[str, Dict[str, Any]] = {}
            for p in propiedades:
                unicos.setdefault(p["property_id"], p)
            propiedades = list(unicos.values())

            # Enriquecer con descripción + coords del JSON-LD del detalle
            sem = asyncio.Semaphore(CONCURRENCIA_DETALLE)

            async def _enriquecer(prop: Dict[str, Any]):
                async with sem:
                    det = await self._extraer_detalle(session, prop["url"])
                    if det:
                        if det.get("descripcion"):
                            prop["descripcion"] = det["descripcion"]
                        if det.get("coordenadas"):
                            prop["coordenadas"] = det["coordenadas"]
                        if det.get("superficie_m2") and not prop["terreno"].get("superficie_m2"):
                            prop["terreno"]["superficie_m2"] = det["superficie_m2"]
                            prop["caracteristicas"]["superficie_m2"] = det["superficie_m2"]

            await asyncio.gather(*[_enriquecer(p) for p in propiedades])

            for prop in propiedades:
                try:
                    with open(self.json_dir / f"{self.site_name}_{prop['property_id']}.json", "w", encoding="utf-8") as f:
                        json.dump(prop, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

            return propiedades

    # ---------- Listado ----------

    def _segmentar_cards(self, html: str) -> List[str]:
        segs = re.split(r'(?=<div class="col-lg-3 col-md-6")', html)
        return [s for s in segs if re.search(r'/terreno-[a-z0-9\-]+/\d+', s)]

    def _mapear_card(self, b: str) -> Optional[Dict[str, Any]]:
        link = re.search(r'(https://palmazinmobiliaria\.com/terreno-[a-z0-9\-]+/(\d+))', b)
        if not link:
            return None
        url, pid = link.group(1), link.group(2)

        titulo = None
        mt = re.search(r'<h2>\s*<a[^>]*>([^<]+)</a>', b)
        if mt:
            titulo = unescape(mt.group(1)).strip() or None

        ubic = None
        mu = re.search(r'class="ubicacion[^"]*"[^>]*>([^<]+)', b)
        if mu:
            ubic = unescape(mu.group(1)).strip() or None

        precio = None
        moneda = "MXN"
        precio_a_consultar = False
        mp = re.search(r'<p class="[^"]*t8-title[^"]*">\s*\$?\s*([\d,]+)\s*<small>\s*([A-Z]{3})', b)
        if not mp:
            mp = re.search(r'\$\s*([\d,]+)\s*<small>\s*([A-Z]{3})', b)
        if mp:
            moneda = mp.group(2)
            try:
                num = int(mp.group(1).replace(",", ""))
            except ValueError:
                num = 0
            # Precios simbólicos/placeholder (el agente no puso precio real):
            # implausibles para un inmueble → "a consultar"
            umbral = 50000 if moneda == "MXN" else 3000
            if num >= umbral:
                precio = f"${mp.group(1)} {moneda}"
            else:
                precio_a_consultar = True

        img = re.search(r'src="(https://image\.wasi\.co/[^"]+)"', b)
        imagenes = [img.group(1)] if img else []

        # Superficie m² si aparece en el bloque (info_details)
        terreno: Dict[str, Any] = {}
        caracteristicas: Dict[str, Any] = {}
        ms = re.search(r'([\d,\.]+)\s*m[²2]\b', b)
        if ms:
            try:
                v = float(ms.group(1).replace(",", ""))
                if v > 0:
                    terreno["superficie_m2"] = v
                    caracteristicas["superficie_m2"] = v
            except ValueError:
                pass
        if precio_a_consultar:
            caracteristicas["precio_a_consultar"] = True

        return {
            "url": url,
            "site": self.site_name,
            "property_id": str(pid),
            "empresa": "Palmaz Inmobiliaria",
            "titulo": titulo,
            "ubicacion": ubic or "Mazatlán, Sinaloa",
            "precio": precio,
            "precio_normalizado": self.normalizer.normalizar_precio(precio) if precio else None,
            "moneda": moneda,
            "estado": "En venta",
            "tipo_propiedad": "terreno",
            "terreno": terreno,
            "caracteristicas": caracteristicas,
            "descripcion": None,
            "agente": {},
            "coordenadas": {},
            "imagenes": imagenes,
            "imagenes_descargadas": [],
        }

    # ---------- Detalle (JSON-LD: descripción + coords) ----------

    async def _extraer_detalle(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict[str, Any]]:
        html = await self._get(session, url)
        if not html:
            return None
        m = _LD_RE.search(html)
        if not m:
            return None
        try:
            ld = json.loads(m.group(1).strip())
        except Exception:
            return None

        out: Dict[str, Any] = {}
        desc = ld.get("description")
        if isinstance(desc, str) and desc.strip():
            txt = unescape(re.sub(r"<[^>]+>", " ", desc))
            txt = re.sub(r"\s+", " ", txt).strip()
            if txt:
                out["descripcion"] = txt
                ms = re.search(r'([\d,\.]+)\s*m[²2]\b', txt)
                if ms:
                    try:
                        out["superficie_m2"] = float(ms.group(1).replace(",", ""))
                    except ValueError:
                        pass

        geo = ld.get("geo")
        if isinstance(geo, dict) and geo.get("latitude"):
            out["coordenadas"] = {"lat": geo.get("latitude"), "lng": geo.get("longitude")}
        return out

    # ---------- Utilidades ----------

    async def _get(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return None
                return await resp.text()
        except Exception:
            return None


async def main():
    scraper = PalmazScraper(output_dir="data")
    props = await scraper.extraer_todas_las_propiedades()
    print(f"\n✅ {len(props)} propiedades extraídas")
    print(f"sin precio: {len([p for p in props if not p['precio']])} | con desc: {len([p for p in props if p.get('descripcion')])} | con img: {len([p for p in props if p.get('imagenes')])} | con coords: {len([p for p in props if p.get('coordenadas')])}")
    for p in props[:3]:
        print(f"  [{p['property_id']}] {(p['titulo'] or '')[:42]} | {p['precio']} | {p['terreno']} | imgs={len(p.get('imagenes',[]))}")


if __name__ == "__main__":
    asyncio.run(main())
