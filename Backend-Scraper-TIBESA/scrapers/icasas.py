"""
Scraper para iCasas (https://www.icasas.mx) — AGREGADOR.

iCasas es un portal de la red Lifull Connect (igual que Mitula y Trovit): no tiene
inventario propio, recopila anuncios de inmobiliarias y otros portales, por lo que
puede DUPLICAR propiedades ya presentes en los otros scrapers. El enlace de detalle
(`/propiedad/...`) es una ficha de iCasas que redirige/contacta a la fuente.

A diferencia de Trovit, iCasas SÍ responde con HTTP plano (200) y sirve todo el
listado renderizado en el servidor con microdata schema.org embebida en cada
`<li class="serp-snippet ad ...">`: precio, título, link, descripción, agencia,
dirección (PostalAddress) y geo (GeoCoordinates). Por eso se scrapea con **HTTP puro
(aiohttp) + regex sobre el microdata**, el flujo más rápido y robusto (como
Casas y Terrenos), sin Playwright.

Paginación: `/p_N` (30 anuncios por página). Se itera hasta que una página trae
menos de 30 anuncios o repite ids ya vistos.
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from utils.data_normalizer import DataNormalizer

BASE = "https://www.icasas.mx"
# Terrenos/lotes en venta en Mazatlán, Sinaloa
LISTADO_URL = f"{BASE}/venta/tierras-lotes-terrenos-sinaloa-mazatlan-5_9_25_0_1875_0"
MAX_PAGINAS = 15
POR_PAGINA = 30

# Cada bloque de anuncio en el listado (SSR, microdata schema.org)
_AD_SPLIT_RE = re.compile(r'(?=<li class="serp-snippet ad)')
_AD_ID_RE = re.compile(r'<li class="serp-snippet ad[^"]*"\s+id="([0-9a-f\-]+)"')


class IcasasScraper:
    """Scraper de listado (HTTP plano + microdata) para el agregador iCasas."""

    LISTADO_URL = LISTADO_URL

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    def __init__(self, output_dir: str = "data", headless: bool = True):
        self.output_dir = Path(output_dir)
        self.json_dir = self.output_dir / "json"
        self.images_dir = self.output_dir / "imagenes"
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless  # no se usa (sin navegador); se mantiene por compatibilidad
        self.site_name = "icasas"
        self.normalizer = DataNormalizer()

    # ---------- API pública (consumida por _event_generator_listing) ----------

    async def extraer_todas_las_propiedades(self, callback=None, max_pages: int = 0) -> List[Dict[str, Any]]:
        propiedades: List[Dict[str, Any]] = []
        vistos = set()
        tope = max_pages or MAX_PAGINAS

        async with aiohttp.ClientSession(headers=self.DEFAULT_HEADERS) as session:
            for num in range(1, tope + 1):
                url = self.LISTADO_URL if num == 1 else f"{self.LISTADO_URL}/p_{num}"
                html = await self._descargar(session, url)
                if not html:
                    break

                crudas = self._extraer_cards(html)
                nuevas = [c for c in crudas if c.get("pid") and c["pid"] not in vistos]
                if not nuevas:
                    break

                for c in nuevas:
                    vistos.add(c["pid"])
                    prop = self._mapear(c)
                    if prop:
                        propiedades.append(prop)
                        try:
                            with open(self.json_dir / f"{self.site_name}_{prop['property_id']}.json",
                                      "w", encoding="utf-8") as f:
                                json.dump(prop, f, indent=2, ensure_ascii=False)
                        except Exception:
                            pass

                # Página con menos de 30 anuncios → última página
                if len(crudas) < POR_PAGINA:
                    break

        return propiedades

    # ---------- Descarga ----------

    async def _descargar(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return None
                return await resp.text()
        except Exception:
            return None

    # ---------- Parseo del listado ----------

    def _extraer_cards(self, html: str) -> List[Dict[str, Any]]:
        """Parte el HTML en bloques `<li class="serp-snippet ad ...">` y extrae sus campos crudos."""
        cards: List[Dict[str, Any]] = []
        for bloque in _AD_SPLIT_RE.split(html):
            m = _AD_ID_RE.match(bloque)
            if not m:
                continue
            fin = bloque.find("</li>")
            block = bloque[:fin + 5] if fin > 0 else bloque[:5000]
            cards.append(self._parse_block(m.group(1), block))
        return cards

    @staticmethod
    def _buscar(patron: str, texto: str) -> Optional[str]:
        m = re.search(patron, texto, re.S)
        return m.group(1).strip() if m else None

    def _parse_block(self, pid: str, block: str) -> Dict[str, Any]:
        desc = self._buscar(r'itemprop="description"[^>]*>(.*?)</p>', block)
        if desc:
            desc = re.sub(r'<[^>]+>', '', desc).strip()
        return {
            "pid": pid,
            "href": self._buscar(r'class="detail-redirection"[^>]*href="([^"]+)"', block),
            "titulo": self._buscar(r'class="detail-redirection"[^>]*>([^<]+)<', block),
            "precio_raw": self._buscar(r'<div class="price">\s*([^<]+?)\s*<', block),
            "agencia": self._buscar(r'RealEstateAgent".*?<meta itemprop="name" content="([^"]+)"', block),
            "locality": self._buscar(r'itemprop="addressLocality" content="([^"]+)"', block),
            "region": self._buscar(r'itemprop="addressRegion" content="([^"]+)"', block),
            "street": self._buscar(r'itemprop="streetAddress" content="([^"]+)"', block),
            "lat": self._buscar(r'itemprop="latitude" content="([^"]+)"', block),
            "lon": self._buscar(r'itemprop="longitude" content="([^"]+)"', block),
            "imagen": self._buscar(r'<div class="slider-ad">\s*<img src="([^"]+)"', block),
            "descripcion": desc,
        }

    def _mapear(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            pid = raw.get("pid")
            if not pid:
                return None

            titulo = (raw.get("titulo") or "").strip() or None

            # Precio + moneda. Formato del portal: "1,200,000 MX$" / "345,000 US$"
            precio = None
            moneda = "MXN"
            ptxt = raw.get("precio_raw") or ""
            mnum = re.search(r'([\d.,]+)', ptxt)
            if mnum:
                cur = "USD" if re.search(r'US\$|USD|d[óo]lar', ptxt, re.I) else "MXN"
                moneda = cur
                precio = f"${mnum.group(1)} {cur}"

            # Ubicación legible
            ubic_partes = [raw.get("locality"), raw.get("region")]
            ubicacion = ", ".join(p for p in ubic_partes if p) or raw.get("street") or "Mazatlán, Sinaloa"

            # Coordenadas
            coordenadas: Dict[str, Any] = {}
            try:
                if raw.get("lat") and raw.get("lon"):
                    coordenadas = {"lat": float(raw["lat"]), "lng": float(raw["lon"])}
            except (ValueError, TypeError):
                coordenadas = {}

            # Superficie m² desde título/descripción (terrenos no la traen estructurada)
            terreno: Dict[str, Any] = {}
            caracteristicas: Dict[str, Any] = {}
            blob = f"{titulo or ''} {raw.get('descripcion') or ''}"
            ms = re.search(r'([\d.,]+)\s*m[²2]\b', blob)
            if ms:
                try:
                    sup = float(ms.group(1).replace(",", ""))
                    if sup > 0:
                        terreno["superficie_m2"] = sup
                        caracteristicas["superficie_m2"] = sup
                except ValueError:
                    pass

            descripcion = raw.get("descripcion") or None

            agencia = raw.get("agencia")
            agente = {"oficina": agencia} if agencia else {}

            href = raw.get("href") or ""
            url = f"{BASE}{href}" if href.startswith("/") else href

            imagen = raw.get("imagen")
            imagenes = [imagen] if imagen and imagen.startswith("http") else []

            return {
                "url": url,
                "site": self.site_name,
                "property_id": str(pid),
                "empresa": agencia or "iCasas (agregador)",
                "es_agregador": True,
                "titulo": titulo,
                "ubicacion": ubicacion,
                "zona": raw.get("locality"),
                "precio": precio,
                "precio_normalizado": self.normalizer.normalizar_precio(precio) if precio else None,
                "moneda": moneda,
                "estado": "En venta",
                "tipo_propiedad": self._normalizar_tipo(titulo),
                "terreno": terreno,
                "caracteristicas": caracteristicas,
                "descripcion": descripcion,
                "agente": agente,
                "coordenadas": coordenadas,
                "imagenes": imagenes,
                "imagenes_descargadas": [],
            }
        except Exception:
            return None

    @staticmethod
    def _normalizar_tipo(titulo: Optional[str]) -> Optional[str]:
        t = (titulo or "").lower()
        mapa = {
            "terreno": "terreno", "lote": "terreno", "tierra": "terreno",
            "casa": "casa", "departamento": "departamento", "depto": "departamento",
            "local": "local", "oficina": "oficina", "bodega": "bodega",
            "edificio": "edificio", "rancho": "rancho",
        }
        for clave, valor in mapa.items():
            if clave in t:
                return valor
        return "terreno"  # el listado configurado es de terrenos/lotes


async def main():
    """Prueba rápida del scraper."""
    scraper = IcasasScraper(output_dir="data")
    props = await scraper.extraer_todas_las_propiedades()
    print(f"\n✅ {len(props)} propiedades extraídas")
    sin_p = [p for p in props if not p["precio"]]
    con_d = [p for p in props if p.get("descripcion")]
    con_m2 = [p for p in props if p.get("terreno", {}).get("superficie_m2")]
    print(f"sin precio: {len(sin_p)} | con descripción: {len(con_d)} | con m²: {len(con_m2)}")
    if props:
        p = props[0]
        print(json.dumps({k: p[k] for k in ("titulo", "precio", "ubicacion", "tipo_propiedad",
                                            "terreno", "coordenadas", "property_id", "url", "empresa")},
                         indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
