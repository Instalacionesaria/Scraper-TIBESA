"""
Scraper para Mazatlán Bienes Raíces en Venta (https://mazatlanbienesraicesenventa.com)

Inmobiliaria directa (no agregador), sitio PHP/CodeIgniter SIN anti-bot
(HTTP 200 plano). Se scrapea con HTTP puro (aiohttp), sin Playwright.

- Inventario pequeño (categoría lotes: ~7 propiedades, sin paginación).
- Datos básicos en las tarjetas del listado: título (`.linecondos`), precio
  (`.list-price`), atributos (Estado/Proyecto/Estilo/M2), imagen y link
  `/propiedad/{slug}/{id}`.
- La descripción rica y la galería se toman de la ficha de detalle (las imágenes
  viven en el dominio hermano `mazatlanrealestateguide.com`, nombradas `{id}_...`).
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from utils.data_normalizer import DataNormalizer

BASE = "https://mazatlanbienesraicesenventa.com"
LISTADO_URL = f"{BASE}/lotes/en-venta"
CONCURRENCIA_DETALLE = 5


class MazatlanBienesRaicesScraper:
    """Scraper de listado (HTTP plano) para Mazatlán Bienes Raíces en Venta."""

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
        self.site_name = "mazatlan_bienes_raices"
        self.normalizer = DataNormalizer()

    # ---------- API pública (consumida por _event_generator_listing) ----------

    async def extraer_todas_las_propiedades(self, callback=None, max_pages: int = 0) -> List[Dict[str, Any]]:
        async with aiohttp.ClientSession(headers=self.DEFAULT_HEADERS) as session:
            html = await self._get(session, self.LISTADO_URL)
            if not html:
                return []
            propiedades = [self._mapear_card(b) for b in self._segmentar_cards(html)]
            propiedades = [p for p in propiedades if p]

            # Dedup por property_id (el listado repite link en ES/EN)
            unicos: Dict[str, Dict[str, Any]] = {}
            for p in propiedades:
                unicos.setdefault(p["property_id"], p)
            propiedades = list(unicos.values())

            # Enriquecer con descripción + imágenes del detalle (en paralelo)
            sem = asyncio.Semaphore(CONCURRENCIA_DETALLE)

            async def _enriquecer(prop: Dict[str, Any]):
                async with sem:
                    det = await self._extraer_detalle(session, prop["url"], prop["property_id"])
                    if det:
                        if det.get("descripcion"):
                            prop["descripcion"] = det["descripcion"]
                        if det.get("imagenes"):
                            prop["imagenes"] = det["imagenes"]

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
        bloques = re.split(r'(?=<div class="linecondos")', html)
        return [b for b in bloques if "list-price" in b and "/propiedad/" in b]

    def _mapear_card(self, b: str) -> Optional[Dict[str, Any]]:
        def m(pat, g=1, flags=0):
            x = re.search(pat, b, flags)
            return x.group(g).strip() if x else None

        link = re.search(r'/propiedad/([a-z0-9\-]+)/(\d+)"', b)
        if not link:
            return None
        slug, pid = link.group(1), link.group(2)
        url = f"{BASE}/propiedad/{slug}/{pid}"

        titulo = m(r'class="linecondos"[^>]*>([^<]+)<')

        precio = None
        moneda = "MXN"
        pm = re.search(r'list-price">\s*\$?\s*([\d,\.]+)\s*([A-Z]{3})?', b)
        if pm:
            num = pm.group(1).rstrip(".0").replace(",", "") if pm.group(1) else ""
            num_fmt = pm.group(1).split(".")[0]  # quitar decimales ".00"
            moneda = pm.group(2) or "MXN"
            if num_fmt:
                precio = f"${num_fmt} {moneda}"

        # Superficie: M2 del listado o hectáreas del título
        terreno: Dict[str, Any] = {}
        caracteristicas: Dict[str, Any] = {}
        m2 = m(r'M2:</b>\s*([\d,\.]+)')
        if m2:
            try:
                v = float(m2.replace(",", ""))
                if v > 0:
                    terreno["superficie_m2"] = v
                    caracteristicas["superficie_m2"] = v
            except ValueError:
                pass
        if titulo:
            hect = re.search(r'([\d,\.]+)\s*HECT', titulo, re.I)
            if hect:
                try:
                    caracteristicas["hectareas"] = float(hect.group(1).replace(",", ""))
                except ValueError:
                    pass

        estado = m(r'Estado:</b>\s*([^<]+)<')
        proyecto = m(r'Proyecto:</b>\s*([^<]+)<')
        for clave, val in (("estado_obra", estado), ("proyecto", proyecto)):
            if val:
                caracteristicas[clave] = val.strip()

        img = m(r'src="(//[^"]+archivos[^"]+\.(?:jpg|jpeg|png|webp))"')
        imagenes = [f"https:{img}"] if img and img.startswith("//") else ([img] if img else [])

        return {
            "url": url,
            "site": self.site_name,
            "property_id": str(pid),
            "empresa": "Mazatlán Bienes Raíces",
            "titulo": titulo,
            "ubicacion": "Mazatlán, Sinaloa",
            "precio": precio,
            "precio_normalizado": self.normalizer.normalizar_precio(precio) if precio else None,
            "moneda": moneda,
            "estado": "En venta",
            "tipo_propiedad": "terreno",
            "terreno": terreno,
            "caracteristicas": caracteristicas,
            "descripcion": None,
            "agente": {},
            "imagenes": imagenes,
            "imagenes_descargadas": [],
        }

    # ---------- Detalle (descripción + galería) ----------

    async def _extraer_detalle(self, session: aiohttp.ClientSession, url: str, pid: str) -> Optional[Dict[str, Any]]:
        html = await self._get(session, url)
        if not html:
            return None
        out: Dict[str, Any] = {}

        # Descripción: el bloque de texto más largo relevante
        mejor = ""
        for mm in re.finditer(r'<(div|section|td|p)[^>]*>(.*?)</\1>', html, re.S):
            txt = re.sub(r'<[^>]+>', '', mm.group(2))
            txt = re.sub(r'\s+', ' ', txt).strip()
            if 120 < len(txt) < 2500 and re.search(r'lote|terreno|venta|mazatl|desarrollo|amenidad', txt, re.I):
                if len(txt) > len(mejor):
                    mejor = txt
        if mejor:
            out["descripcion"] = mejor

        # Imágenes de ESTA propiedad (nombradas {id}_... en el dominio de archivos)
        imgs = []
        for u in re.findall(r'(//[^"\']+/archivos[^"\']+\.(?:jpg|jpeg|png|webp))', html, re.I):
            if f"/{pid}_" in u or re.search(rf'/{pid}_', u):
                full = f"https:{u}" if u.startswith("//") else u
                if full not in imgs:
                    imgs.append(full)
        if imgs:
            out["imagenes"] = imgs
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
    scraper = MazatlanBienesRaicesScraper(output_dir="data")
    props = await scraper.extraer_todas_las_propiedades()
    print(f"\n✅ {len(props)} propiedades extraídas")
    sin_p = [p for p in props if not p["precio"]]
    con_d = [p for p in props if p.get("descripcion")]
    con_i = [p for p in props if p.get("imagenes")]
    print(f"sin precio: {len(sin_p)} | con descripción: {len(con_d)} | con imágenes: {len(con_i)}")
    for p in props[:3]:
        print(f"  [{p['property_id']}] {(p['titulo'] or '')[:45]} | {p['precio']} | imgs={len(p.get('imagenes',[]))}")


if __name__ == "__main__":
    asyncio.run(main())
