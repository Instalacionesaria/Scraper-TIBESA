"""
Scraper para Spezia Mazatlán (https://www.speziamazatlan.com.mx)

Inmobiliaria directa (tema WordPress "Inwave"), SIN anti-bot (HTTP 200 plano).
Se scrapea con HTTP puro (aiohttp), sin Playwright.

- Inventario pequeño. La categoría de terrenos lista las fichas en
  `/inmuebles/{slug}/`. No hay paginación numérica visible (pocas propiedades).
- Los datos ricos están en la ficha de detalle (no en tarjetas): precio en
  `.property-price .main-price`, descripción en `.iwp-single-property-description`
  (itemprop=description, incluye la superficie en m²), galería en wp-content/uploads.
- NOTA: Spezia es una de las agencias que Pincali agrega, así que parte del
  inventario puede solaparse con [[scraper-pincali]] (mismos slugs). Aun así es la
  fuente primaria (la inmobiliaria directa).
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from utils.data_normalizer import DataNormalizer

BASE = "https://www.speziamazatlan.com.mx"
LISTADO_URL = f"{BASE}/inmuebles/terrenos-residenciales-en-venta-en-mazatlan/"
CONCURRENCIA_DETALLE = 5
MAX_PAGINAS = 10


class SpeziaScraper:
    """Scraper de listado (HTTP plano + WordPress Inwave) para Spezia Mazatlán."""

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
        self.site_name = "spezia"
        self.normalizer = DataNormalizer()

    # ---------- API pública (consumida por _event_generator_listing) ----------

    async def extraer_todas_las_propiedades(self, callback=None, max_pages: int = 0) -> List[Dict[str, Any]]:
        async with aiohttp.ClientSession(headers=self.DEFAULT_HEADERS) as session:
            # 1) Recolectar URLs de fichas paginando /page/N/ hasta que no haya nuevas
            urls: List[str] = []
            vistos = set()
            tope = max_pages or MAX_PAGINAS
            for pagina in range(1, tope + 1):
                url = self.LISTADO_URL if pagina == 1 else f"{self.LISTADO_URL}page/{pagina}/"
                html = await self._get(session, url)
                if not html:
                    break
                nuevas = [u for u in self._extraer_urls_fichas(html) if u not in vistos]
                if not nuevas:
                    break
                for u in nuevas:
                    vistos.add(u)
                    urls.append(u)

            # 2) Scrapear cada ficha de detalle en paralelo
            sem = asyncio.Semaphore(CONCURRENCIA_DETALLE)

            async def _ficha(u: str):
                async with sem:
                    return await self._extraer_detalle(session, u)

            resultados = await asyncio.gather(*[_ficha(u) for u in urls])
            propiedades = [r for r in resultados if r]

            for prop in propiedades:
                try:
                    with open(self.json_dir / f"{self.site_name}_{prop['property_id']}.json", "w", encoding="utf-8") as f:
                        json.dump(prop, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

            return propiedades

    # ---------- Listado ----------

    def _extraer_urls_fichas(self, html: str) -> List[str]:
        slugs = re.findall(r'https://www\.speziamazatlan\.com\.mx/inmuebles/([a-z0-9%À-ſ\-]+)/', html)
        out, seen = [], set()
        for s in slugs:
            # excluir la propia categoría y duplicados
            if s.startswith("terrenos-residenciales") or "en-venta-en-mazatlan" == s:
                continue
            if s in seen:
                continue
            seen.add(s)
            out.append(f"{BASE}/inmuebles/{s}/")
        return out

    # ---------- Detalle ----------

    async def _extraer_detalle(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict[str, Any]]:
        html = await self._get(session, url)
        if not html:
            return None

        slug = re.search(r'/inmuebles/([^/?#]+)/', url)
        slug = slug.group(1) if slug else url

        # Título: del <title>, quitando el sufijo del sitio
        titulo = None
        mt = re.search(r'<title>(.*?)</title>', html, re.S)
        if mt:
            titulo = re.sub(r'\s*[–\-&#8211;]+\s*Spezia Mazatl[aá]n.*$', '', mt.group(1)).strip()
            titulo = re.sub(r'&#8211;|&#8217;', '', titulo).strip(" .–-") or None

        # Precio: .property-price .main-price → "MX$3,700,000"
        precio = None
        moneda = "MXN"
        pm = re.search(r'class="main-price"[^>]*>\s*(?:MX)?\$?\s*([\d,]+)', html)
        if pm:
            precio = f"${pm.group(1)} {moneda}"

        # Descripción (itemprop=description), texto limpio
        descripcion = None
        dm = re.search(r'class="iwp-single-property-description"[^>]*>(.*?)</div>', html, re.S)
        if dm:
            txt = re.sub(r'<[^>]+>', ' ', dm.group(1))
            txt = re.sub(r'\s+', ' ', txt).strip()
            descripcion = txt or None

        # Superficie m² desde la descripción/título
        terreno: Dict[str, Any] = {}
        caracteristicas: Dict[str, Any] = {}
        blob = f"{titulo or ''} {descripcion or ''}"
        ms = re.search(r'([\d.,]+)\s*m[²2]\b', blob)
        if ms:
            try:
                sup = float(ms.group(1).replace(",", ""))
                terreno["superficie_m2"] = sup
                caracteristicas["superficie_m2"] = sup
            except ValueError:
                pass

        # Imágenes: galería antes de la sección "Propiedades relacionadas"
        cuerpo = re.split(r'property-related', html, 1)[0]
        imgs: List[str] = []
        for u in re.findall(r'https://www\.speziamazatlan\.com\.mx/wp-content/uploads/[^\s"\']+\.(?:jpg|jpeg|png|webp)', cuerpo, re.I):
            base = re.sub(r'-\d+x\d+(?=\.[a-z]+$)', '', u.split("?")[0])
            low = base.lower()
            if any(x in low for x in ("isotipo", "logo", "favicon", "icon", "avatar", "cropped-", "placeholder")):
                continue
            if base not in imgs:
                imgs.append(base)

        return {
            "url": url,
            "site": self.site_name,
            "property_id": slug,
            "empresa": "Spezia Mazatlán",
            "titulo": titulo,
            "ubicacion": "Mazatlán, Sinaloa",
            "precio": precio,
            "precio_normalizado": self.normalizer.normalizar_precio(precio) if precio else None,
            "moneda": moneda,
            "estado": "En venta",
            "tipo_propiedad": self._inferir_tipo(slug, titulo),
            "terreno": terreno,
            "caracteristicas": caracteristicas,
            "descripcion": descripcion,
            "agente": {},
            "imagenes": imgs,
            "imagenes_descargadas": [],
        }

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
    def _inferir_tipo(slug: str, titulo: Optional[str]) -> Optional[str]:
        t = f"{slug} {titulo or ''}".lower()
        mapa = {
            "terreno": "terreno", "lote": "terreno",
            "casa": "casa", "departamento": "departamento", "depto": "departamento",
            "condominio": "condominio", "local": "local", "oficina": "oficina",
        }
        for clave, valor in mapa.items():
            if clave in t:
                return valor
        return "terreno"


async def main():
    scraper = SpeziaScraper(output_dir="data")
    props = await scraper.extraer_todas_las_propiedades()
    print(f"\n✅ {len(props)} propiedades extraídas")
    print(f"sin precio: {len([p for p in props if not p['precio']])} | con desc: {len([p for p in props if p.get('descripcion')])} | con img: {len([p for p in props if p.get('imagenes')])}")
    for p in props[:4]:
        print(f"  [{p['tipo_propiedad']}] {(p['titulo'] or '')[:45]} | {p['precio']} | {p['terreno']} | imgs={len(p.get('imagenes',[]))}")


if __name__ == "__main__":
    asyncio.run(main())
