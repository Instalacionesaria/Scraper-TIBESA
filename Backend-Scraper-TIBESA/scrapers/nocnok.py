"""
Scraper para NocNok (https://inmuebles.nocnok.com) — portal inmobiliario.

NocNok es un Next.js (Pages Router) cuyo `__NEXT_DATA__` solo trae filtros, no las
propiedades: el listado se sirve por su **API JSON pública del mismo dominio**
(`/api/properties/search`), sin autenticación. Responde HTTP 200 plano → se scrapea
con **HTTP puro (aiohttp)** golpeando esa API (sin navegador), el patrón más rápido.

La respuesta del search YA trae todo lo necesario por propiedad (título, descripción,
precio, lotSize en m², ubicación, geolocalización, fotos, url), así que NO hace falta
pedir ficha de detalle.

Filtro de Mazatlán (descubierto del bundle JS): `operation=sale`, `stateId=25`
(Sinaloa), `countyIds=1882` (Mazatlán), `types=Land`. Paginación `pageNumber`/
`pageSize` (la respuesta trae `paging.totalCount`). ~74 terrenos.
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from utils.data_normalizer import DataNormalizer

BASE = "https://inmuebles.nocnok.com"
SEARCH = f"{BASE}/api/properties/search"
PAGE_SIZE = 50
MAX_PAGINAS = 20

# Filtros del área de Mazatlán (Sinaloa), terrenos en venta
PARAMS_BASE = {
    "operation": "sale",
    "stateId": "25",       # Sinaloa
    "countyIds": "1882",   # Mazatlán
    "types": "Land",       # Terrenos
    "pageSize": str(PAGE_SIZE),
}


class NocNokScraper:
    """Scraper de NocNok vía su API JSON pública (HTTP plano, sin navegador)."""

    LISTADO_URL = f"{BASE}/s/terreno-en-venta/sinaloa/mazatlan"

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
        "Referer": f"{BASE}/",
    }

    def __init__(self, output_dir: str = "data", headless: bool = True):
        self.output_dir = Path(output_dir)
        self.json_dir = self.output_dir / "json"
        self.images_dir = self.output_dir / "imagenes"
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless  # no se usa (sin navegador); se mantiene por compatibilidad
        self.site_name = "nocnok"
        self.normalizer = DataNormalizer()

    # ---------- API pública (consumida por _event_generator_listing) ----------

    async def extraer_todas_las_propiedades(self, callback=None, max_pages: int = 0) -> List[Dict[str, Any]]:
        propiedades: List[Dict[str, Any]] = []
        vistos = set()
        tope = max_pages or MAX_PAGINAS

        async with aiohttp.ClientSession(headers=self.DEFAULT_HEADERS) as session:
            for num in range(1, tope + 1):
                payload = await self._buscar_pagina(session, num)
                if not payload:
                    break
                items = payload.get("data") or []
                if not items:
                    break

                nuevas = [it for it in items if it.get("id") and it["id"] not in vistos]
                for it in nuevas:
                    vistos.add(it["id"])
                    prop = self._mapear(it)
                    if prop:
                        propiedades.append(prop)
                        try:
                            with open(self.json_dir / f"{self.site_name}_{prop['property_id']}.json",
                                      "w", encoding="utf-8") as f:
                                json.dump(prop, f, indent=2, ensure_ascii=False)
                        except Exception:
                            pass

                # ¿Última página? (alcanzado el total o página incompleta)
                paging = payload.get("paging") or {}
                total = paging.get("totalCount")
                if (total and len(vistos) >= total) or len(items) < PAGE_SIZE:
                    break

        return propiedades

    async def _buscar_pagina(self, session: aiohttp.ClientSession, num: int) -> Optional[Dict[str, Any]]:
        params = {**PARAMS_BASE, "pageNumber": str(num)}
        try:
            async with session.get(SEARCH, params=params,
                                   timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
        except Exception:
            return None

    # ---------- Mapeo ----------

    def _mapear(self, it: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            pid = it.get("id") or it.get("code")
            if not pid:
                return None

            titulo = (it.get("title") or "").strip() or None

            # Precio + moneda. Formato del portal: "298,000,000 MXN"
            precio = None
            moneda = "MXN"
            ptxt = it.get("price") or ""
            mnum = re.search(r'([\d.,]+)', ptxt)
            if mnum:
                cur = "USD" if re.search(r'USD|US\$|d[óo]lar', ptxt, re.I) else "MXN"
                moneda = cur
                precio = f"${mnum.group(1)} {cur}"

            # Superficie del terreno: lotSize "60,000 m²"
            terreno: Dict[str, Any] = {}
            caracteristicas: Dict[str, Any] = {}
            sup = self._m2(it.get("lotSize")) or self._m2(it.get("constructionSize"))
            if sup:
                terreno["superficie_m2"] = sup
                caracteristicas["superficie_m2"] = sup

            # Coordenadas
            coordenadas: Dict[str, Any] = {}
            geo = it.get("geolocation") or {}
            try:
                if geo.get("lat") and geo.get("lon"):
                    coordenadas = {"lat": float(geo["lat"]), "lng": float(geo["lon"])}
            except (ValueError, TypeError):
                coordenadas = {}

            imagenes = [p for p in (it.get("pictures") or []) if isinstance(p, str) and p.startswith("http")]

            # Agencia / cuenta (a veces es el placeholder "Name")
            agente = {}
            cuenta = it.get("account") or {}
            nombre = cuenta.get("name")
            if nombre and nombre.lower() != "name":
                agente["nombre"] = nombre

            url = it.get("url") or BASE

            return {
                "url": url,
                "site": self.site_name,
                "property_id": str(pid),
                "empresa": (nombre if nombre and nombre.lower() != "name" else "NocNok"),
                "titulo": titulo,
                "ubicacion": it.get("location") or "Mazatlán, Sinaloa",
                "precio": precio,
                "precio_normalizado": self.normalizer.normalizar_precio(precio) if precio else None,
                "moneda": moneda,
                "estado": "En venta",
                "tipo_propiedad": "terreno",
                "terreno": terreno,
                "caracteristicas": caracteristicas,
                "descripcion": (it.get("description") or "").strip() or None,
                "agente": agente,
                "coordenadas": coordenadas,
                "imagenes": imagenes,
                "imagenes_descargadas": [],
            }
        except Exception:
            return None

    @staticmethod
    def _m2(valor: Any) -> Optional[float]:
        """De '60,000 m²' / '136 m²' → 60000.0 / 136.0."""
        if not valor:
            return None
        m = re.search(r'([\d.,]+)', str(valor))
        if not m:
            return None
        try:
            f = float(m.group(1).replace(",", ""))
            return round(f, 2) if f > 0 else None
        except ValueError:
            return None


async def main():
    """Prueba rápida del scraper."""
    scraper = NocNokScraper(output_dir="data")
    props = await scraper.extraer_todas_las_propiedades()
    print(f"\n✅ {len(props)} terrenos extraídos")
    cp = [p for p in props if p["precio"]]
    cd = [p for p in props if p.get("descripcion")]
    cm = [p for p in props if p.get("terreno", {}).get("superficie_m2")]
    ci = [p for p in props if p["imagenes"]]
    print(f"con precio: {len(cp)} | con descripción: {len(cd)} | con m²: {len(cm)} | con imágenes: {len(ci)}")
    if props:
        p = props[0]
        print(json.dumps({k: p[k] for k in ("titulo", "precio", "ubicacion", "terreno", "coordenadas",
                                            "property_id", "url")}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
