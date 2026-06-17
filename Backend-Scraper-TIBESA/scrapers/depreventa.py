"""
Scraper para DePreventa Bienes Raíces (https://depreventa.mx)

Sitio WordPress (Elementor) SIN anti-bot (HTTP 200 plano). Se scrapea con HTTP
puro (aiohttp), sin Playwright.

Estrategia:
- El precio y los datos básicos vienen limpios en las tarjetas del listado
  (`.dp-card`), con `data-listid`, `data-modal-title`, `data-modal-link` y
  `.dp-card__price-amount`. El precio se toma de aquí (en la ficha de detalle se
  mezcla con los valores del slider de filtro).
- La descripción y las fotos se toman de la ficha de detalle `/propiedades/{slug}/`
  vía el JSON-LD `RealEstateListing` (name/description/image) + galería
  `wp-content/uploads`.
- OJO: el JSON-LD `Place` de la ficha es la dirección de la AGENCIA (mismo
  `#place` en todas), NO la ubicación de la propiedad — no se usa.

Categoría de terrenos en Mazatlán: ~15 propiedades, paginado con `/page/N/`.
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from utils.data_normalizer import DataNormalizer

BASE = "https://depreventa.mx"
LISTADO_URL = f"{BASE}/categoria/terrenos/"

CONCURRENCIA_DETALLE = 8
MAX_PAGINAS = 15
_LD_RE = re.compile(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S)


class DepreventaScraper:
    """Scraper de listado (HTTP plano + WordPress) para DePreventa."""

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
        self.headless = headless  # no se usa (sin navegador); compatibilidad
        self.site_name = "depreventa"
        self.normalizer = DataNormalizer()

    # ---------- API pública (consumida por _event_generator_listing) ----------

    async def extraer_todas_las_propiedades(self, callback=None, max_pages: int = 0) -> List[Dict[str, Any]]:
        async with aiohttp.ClientSession(headers=self.DEFAULT_HEADERS) as session:
            # 1) Recorrer páginas del listado y parsear las tarjetas
            propiedades: List[Dict[str, Any]] = []
            vistos = set()
            tope = max_pages or MAX_PAGINAS
            for pagina in range(1, tope + 1):
                url = self.LISTADO_URL if pagina == 1 else f"{self.LISTADO_URL}page/{pagina}/"
                html = await self._get(session, url)
                if not html:
                    break
                cards = self._parsear_cards(html)
                nuevos = [c for c in cards if c["property_id"] not in vistos]
                if not nuevos:
                    break
                for c in nuevos:
                    vistos.add(c["property_id"])
                propiedades.extend(nuevos)
                if len(cards) == 0:
                    break

            # 2) Enriquecer con descripción + imágenes de la ficha de detalle (en paralelo)
            sem = asyncio.Semaphore(CONCURRENCIA_DETALLE)

            async def _enriquecer(prop: Dict[str, Any]):
                async with sem:
                    detalle = await self._extraer_detalle(session, prop["url"])
                    if detalle:
                        if detalle.get("descripcion"):
                            prop["descripcion"] = detalle["descripcion"]
                        if detalle.get("imagenes"):
                            prop["imagenes"] = detalle["imagenes"]

            await asyncio.gather(*[_enriquecer(p) for p in propiedades])

            # 3) Guardar JSON local
            for prop in propiedades:
                try:
                    with open(self.json_dir / f"{self.site_name}_{prop['property_id']}.json", "w", encoding="utf-8") as f:
                        json.dump(prop, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

            return propiedades

    # ---------- Listado (parseo de tarjetas) ----------

    def _parsear_cards(self, html: str) -> List[Dict[str, Any]]:
        segs = re.split(r'(?=<div class="col-md-4[^"]*listing_wrapper)', html)
        cards = []
        for s in segs:
            if 'data-listid="' not in s:
                continue
            card = self._mapear_card(s)
            if card:
                cards.append(card)
        return cards

    def _mapear_card(self, seg: str) -> Optional[Dict[str, Any]]:
        def campo(pat, g=1):
            m = re.search(pat, seg, re.S)
            return m.group(g).strip() if m else None

        pid = campo(r'data-listid="(\d+)"')
        link = campo(r'data-modal-link="([^"]+)"')
        titulo = campo(r'data-modal-title="([^"]+)"')
        if not pid or not link:
            return None

        precio_num = campo(r'dp-card__price-amount">\s*\$?\s*([\d,]+)')
        moneda = campo(r'dp-card__price-currency">\s*([A-Za-z]+)') or "MXN"
        precio = None
        if precio_num:
            precio = f"${precio_num} {moneda}".replace("  ", " ")

        # Superficie m² desde el título ("Terreno de 332 m² en ...")
        terreno: Dict[str, Any] = {}
        caracteristicas: Dict[str, Any] = {}
        if titulo:
            m = re.search(r'([\d,.]+)\s*[Mm]²', titulo)
            if m:
                try:
                    sup = float(m.group(1).replace(",", ""))
                    terreno["superficie_m2"] = sup
                    caracteristicas["superficie_m2"] = sup
                except ValueError:
                    pass

        return {
            "url": link,
            "site": self.site_name,
            "property_id": str(pid),
            "empresa": "DePreventa Bienes Raíces",
            "titulo": titulo,
            "ubicacion": "Mazatlán, Sinaloa",  # el portal es exclusivo de Mazatlán
            "precio": precio,
            "precio_normalizado": self.normalizer.normalizar_precio(precio) if precio else None,
            "moneda": moneda,
            "estado": "En venta",
            "tipo_propiedad": self._inferir_tipo(titulo),
            "terreno": terreno,
            "caracteristicas": caracteristicas,
            "descripcion": None,   # se completa con la ficha de detalle
            "agente": {},
            "imagenes": [],
            "imagenes_descargadas": [],
        }

    # ---------- Detalle (descripción + imágenes) ----------

    async def _extraer_detalle(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict[str, Any]]:
        html = await self._get(session, url)
        if not html:
            return None

        out: Dict[str, Any] = {}

        # Descripción desde el JSON-LD RealEstateListing
        for m in _LD_RE.finditer(html):
            try:
                data = json.loads(m.group(1).strip())
            except Exception:
                continue
            items = data.get("@graph", [data]) if isinstance(data, dict) else data
            for it in items:
                if isinstance(it, dict) and it.get("@type") == "RealEstateListing":
                    desc = it.get("description")
                    if isinstance(desc, str) and desc.strip():
                        out["descripcion"] = desc.strip()

        # Imágenes de la propiedad (galería en wp-content/uploads), sin logos/iconos
        imgs = []
        for u in re.findall(r'https://depreventa\.mx/wp-content/uploads/[^\s"\'<>]+\.(?:jpg|jpeg|png|webp)', html):
            base = u.split("?")[0]
            # quitar variantes redimensionadas (-300x187) para deduplicar
            base_norm = re.sub(r'-\d+x\d+(?=\.[a-z]+$)', '', base)
            low = base_norm.lower()
            if any(x in low for x in ("logo", "favisotipo", "favicon", "icono", "icon")):
                continue
            if base_norm not in imgs:
                imgs.append(base_norm)
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

    @staticmethod
    def _inferir_tipo(titulo: Optional[str]) -> Optional[str]:
        t = (titulo or "").lower()
        mapa = {
            "terreno": "terreno", "lote": "terreno",
            "casa": "casa", "departamento": "departamento", "depto": "departamento",
            "local": "local", "oficina": "oficina", "bodega": "bodega",
            "edificio": "edificio",
        }
        for clave, valor in mapa.items():
            if clave in t:
                return valor
        return "terreno"  # la categoría es de terrenos


async def main():
    scraper = DepreventaScraper(output_dir="data")
    props = await scraper.extraer_todas_las_propiedades()
    print(f"\n✅ {len(props)} propiedades extraídas")
    sin_p = [p for p in props if not p["precio"]]
    con_d = [p for p in props if p.get("descripcion")]
    print(f"sin precio: {len(sin_p)} | con descripción: {len(con_d)}")
    if props:
        p = props[0]
        print(json.dumps({k: p[k] for k in ("titulo", "precio", "tipo_propiedad", "terreno",
                                            "property_id", "url")}, indent=2, ensure_ascii=False))
        print("desc:", (p.get("descripcion") or "")[:160])
        print("imgs:", len(p.get("imagenes", [])))


if __name__ == "__main__":
    asyncio.run(main())
