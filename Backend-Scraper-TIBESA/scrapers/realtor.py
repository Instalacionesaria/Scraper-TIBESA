"""
Scraper para Realtor.com International (https://www.realtor.com/international/mx).

Portal internacional de realtor.com (operado por rea.global / Lifull International).
Lista propiedades de México con datos completos renderizados en el servidor: NO usa
`__NEXT_DATA__` (su `pageProps` viene vacío), sino que escribe cada tarjeta
directamente en el HTML (`div.standard-listing-card-non-desktop` + clases `.price`,
`.address`, `.property-type`, `.features`). Responde HTTP 200 con petición plana,
SIN reto anti-bot → se scrapea con **HTTP puro (aiohttp) + regex**, sin navegador
(patrón rápido, como Casas y Terrenos / iCasas).

Ventaja única: trae el **precio en MXN y en USD** a la vez (`.displayListingPrice`
y `.displayConsumerPrice`). La superficie del terreno viene en sq ft → se convierte
a m².

Paginación: `/land/pN` (25 tarjetas por página). El HTML expone `"totalCount"` para
saber cuántas hay (terrenos Mazatlán ≈ 38, o sea 2 páginas).
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from utils.data_normalizer import DataNormalizer

BASE = "https://www.realtor.com"
# Terrenos en venta en Mazatlán, Sinaloa
LISTADO_URL = f"{BASE}/international/mx/mazatlan-sinaloa/land/"
MAX_PAGINAS = 10
POR_PAGINA = 25
SQFT_A_M2 = 0.09290304
ACRE_A_M2 = 4046.8564224

# Link de detalle de cada tarjeta: /international/mx/<slug>-<id>/
_CARD_LINK_RE = re.compile(r'href="(/international/mx/[a-z0-9\-]+-(\d{6,})/)"')
_TOTAL_RE = re.compile(r'"totalCount"\s*:\s*(\d+)')


class RealtorScraper:
    """Scraper de listado (HTTP plano + regex sobre el HTML SSR) para Realtor International."""

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
        self.site_name = "realtor"
        self.normalizer = DataNormalizer()

    # ---------- API pública (consumida por _event_generator_listing) ----------

    async def extraer_todas_las_propiedades(self, callback=None, max_pages: int = 0) -> List[Dict[str, Any]]:
        propiedades: List[Dict[str, Any]] = []
        vistos = set()
        tope = max_pages or MAX_PAGINAS

        async with aiohttp.ClientSession(headers=self.DEFAULT_HEADERS) as session:
            for num in range(1, tope + 1):
                url = self.LISTADO_URL if num == 1 else f"{self.LISTADO_URL}p{num}"
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

                # Cortar al alcanzar el total reportado por el portal, o si la página
                # trajo menos de POR_PAGINA tarjetas (última página).
                total = self._total_reportado(html)
                if (total and len(vistos) >= total) or len(crudas) < POR_PAGINA:
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

    @staticmethod
    def _total_reportado(html: str) -> Optional[int]:
        m = _TOTAL_RE.search(html or "")
        try:
            return int(m.group(1)) if m else None
        except (ValueError, TypeError):
            return None

    # ---------- Parseo del listado ----------

    def _extraer_cards(self, html: str) -> List[Dict[str, Any]]:
        """Localiza los links de tarjeta y trocea el HTML entre uno y el siguiente."""
        # Posición de la primera aparición de cada id (el link envuelve a la tarjeta)
        posiciones: List[tuple] = []
        vistos = set()
        for m in _CARD_LINK_RE.finditer(html):
            url, pid = m.group(1), m.group(2)
            if pid in vistos:
                continue
            vistos.add(pid)
            posiciones.append((m.start(), pid, url))

        cards: List[Dict[str, Any]] = []
        for idx, (pos, pid, url) in enumerate(posiciones):
            fin = posiciones[idx + 1][0] if idx + 1 < len(posiciones) else pos + 4000
            cards.append(self._parse_block(pid, url, html[pos:fin]))
        return cards

    @staticmethod
    def _buscar(patron: str, texto: str) -> Optional[str]:
        m = re.search(patron, texto, re.S)
        return m.group(1).strip() if m else None

    def _parse_block(self, pid: str, url: str, block: str) -> Dict[str, Any]:
        return {
            "pid": pid,
            "url": url,
            "usd": self._buscar(r'displayConsumerPrice">([^<]+)<', block),
            "mxn": self._buscar(r'displayListingPrice">([^<]+)<', block),
            "address": self._buscar(r'class="address">([^<]+)<', block),
            "area": self._buscar(r'<span>([^<]*(?:sq ft|m²|m2|acre)[^<]*)</span>', block),
            "ptype": self._buscar(r'class="property-type">([^<]+)<', block),
            "imagen": self._buscar(r'<img src="(//s1\.rea\.global[^"]+)"', block),
        }

    def _mapear(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            pid = raw.get("pid")
            if not pid:
                return None

            # Precio: MXN como principal (el portal lo provee explícito); USD aparte.
            precio = None
            moneda = "MXN"
            mxn_num = self._solo_numero(raw.get("mxn"))
            if mxn_num:
                precio = f"${mxn_num:,} MXN"
            precio_usd = None
            usd_num = self._solo_numero(raw.get("usd"))
            if usd_num:
                precio_usd = f"${usd_num:,} USD"
            if not precio and precio_usd:  # respaldo si faltara MXN
                precio, moneda = precio_usd, "USD"

            # Superficie del terreno → m²
            terreno: Dict[str, Any] = {}
            caracteristicas: Dict[str, Any] = {}
            sup_m2 = self._area_a_m2(raw.get("area"))
            if sup_m2:
                terreno["superficie_m2"] = sup_m2
                caracteristicas["superficie_m2"] = sup_m2

            imagen = raw.get("imagen")
            imagenes = [f"https:{imagen}"] if imagen and imagen.startswith("//") else (
                [imagen] if imagen and imagen.startswith("http") else []
            )

            href = raw.get("url") or ""
            url = f"{BASE}{href}" if href.startswith("/") else href

            return {
                "url": url,
                "site": self.site_name,
                "property_id": str(pid),
                "empresa": "Realtor.com International",
                "es_agregador": True,
                "titulo": raw.get("address"),
                "ubicacion": raw.get("address") or "Mazatlán, Sinaloa",
                "precio": precio,
                "precio_usd": precio_usd,
                "precio_normalizado": self.normalizer.normalizar_precio(precio) if precio else None,
                "moneda": moneda,
                "estado": "En venta",
                "tipo_propiedad": self._normalizar_tipo(raw.get("ptype")),
                "terreno": terreno,
                "caracteristicas": caracteristicas,
                "descripcion": None,  # el listado no trae descripción de texto libre
                "agente": {},
                "imagenes": imagenes,
                "imagenes_descargadas": [],
            }
        except Exception:
            return None

    @staticmethod
    def _solo_numero(texto: Optional[str]) -> Optional[int]:
        """De 'MXN $2,600,000' / 'USD $149,997' → 2600000 / 149997."""
        if not texto:
            return None
        m = re.search(r'([\d,]+)', texto)
        if not m:
            return None
        try:
            return int(m.group(1).replace(",", ""))
        except ValueError:
            return None

    @staticmethod
    def _area_a_m2(texto: Optional[str]) -> Optional[float]:
        """Convierte '2,865.25 sq ft' / 'X acre' / 'X m²' a m² (1 decimal)."""
        if not texto:
            return None
        m = re.search(r'([\d.,]+)', texto)
        if not m:
            return None
        try:
            valor = float(m.group(1).replace(",", ""))
        except ValueError:
            return None
        t = texto.lower()
        if "sq ft" in t:
            valor *= SQFT_A_M2
        elif "acre" in t:
            valor *= ACRE_A_M2
        # si ya es m²/m2 se deja igual
        return round(valor, 1) if valor > 0 else None

    @staticmethod
    def _normalizar_tipo(ptype: Optional[str]) -> Optional[str]:
        t = (ptype or "").lower()
        mapa = {
            "land": "terreno", "lot": "terreno", "terreno": "terreno",
            "house": "casa", "home": "casa", "casa": "casa",
            "apartment": "departamento", "condo": "departamento", "departamento": "departamento",
            "commercial": "comercial", "office": "oficina",
        }
        for clave, valor in mapa.items():
            if clave in t:
                return valor
        return "terreno"  # el listado configurado es de terrenos (land)


async def main():
    """Prueba rápida del scraper."""
    scraper = RealtorScraper(output_dir="data")
    props = await scraper.extraer_todas_las_propiedades()
    print(f"\n✅ {len(props)} propiedades extraídas")
    con_p = [p for p in props if p["precio"]]
    con_usd = [p for p in props if p.get("precio_usd")]
    con_m2 = [p for p in props if p.get("terreno", {}).get("superficie_m2")]
    print(f"con precio MXN: {len(con_p)} | con USD: {len(con_usd)} | con m²: {len(con_m2)}")
    if props:
        p = props[0]
        print(json.dumps({k: p[k] for k in ("titulo", "precio", "precio_usd", "moneda", "ubicacion",
                                            "tipo_propiedad", "terreno", "property_id", "url")},
                         indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
