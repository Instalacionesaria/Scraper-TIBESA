"""
Scraper para Doorvel (https://www.doorvel.com) — plataforma inmobiliaria.

Doorvel es un Next.js (App Router con RSC) cuyo listado NO está en el HTML: se
carga vía su API pública `api.doorvel.com`. El sitio responde HTTP 200 plano y la
API no exige autenticación para consultar, así que se scrapea con **HTTP puro
(aiohttp)** golpeando directamente la API (sin navegador), el patrón más rápido.

Flujo (2 endpoints, descubiertos del bundle JS):
1. `GET /properties-by-coordinates` con el **polígono (bounds) de Mazatlán** + place_id
   → devuelve TODAS las propiedades del área de una sola vez (sin paginación;
   ~1327 de todos los tipos). Cada item trae datos básicos (id, precio, ubicación,
   lat/lon, property_type_slug).
2. Se filtra client-side por `property_type_slug == "terrenos"` (~126 terrenos) y se
   enriquece cada uno con `GET /properties/{id}` (título, descripción, price_mxn/usd,
   fotos, ubicación detallada, amenidades) en paralelo.

place_id y bounds son constantes geográficas de Mazatlán resueltas por el server del
propio Doorvel a partir del slug "terrenos-en-venta-en-mazatlan-sinaloa-mexico".
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from utils.data_normalizer import DataNormalizer

API = "https://api.doorvel.com"
WEB = "https://www.doorvel.com"

# Área de Mazatlán resuelta por Doorvel (place_id de Google + polígono de respaldo).
MAZATLAN_PLACE_ID = "ChIJwTcYaEFTn4YRsnI88arEpGI"
MAZATLAN_PLACE_NAME = "Mazatlán, Sin., México"
MAZATLAN_BOUNDS = [[[
    [-106.494477359089, 23.17585925338281],
    [-106.3219743657096, 23.17585925338281],
    [-106.3219743657096, 23.31874578912345],
    [-106.494477359089, 23.31874578912345],
    [-106.494477359089, 23.17585925338281],
]]]

# Slugs de tipo que se consideran "terreno" para TIBESA
SLUGS_TERRENO = {"terrenos", "terrenos-comerciales"}

# Fichas de detalle pedidas en paralelo (HTTP plano sin anti-bot → holgado)
CONCURRENCIA_DETALLE = 10


class DoorvelScraper:
    """Scraper de Doorvel vía su API pública (HTTP plano, sin navegador)."""

    LISTADO_URL = f"{WEB}/business/terrenos-en-venta-en-mazatlan-sinaloa-mexico"

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
        "Origin": WEB,
        "Referer": f"{WEB}/",
    }

    def __init__(self, output_dir: str = "data", headless: bool = True):
        self.output_dir = Path(output_dir)
        self.json_dir = self.output_dir / "json"
        self.images_dir = self.output_dir / "imagenes"
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless  # no se usa (sin navegador); se mantiene por compatibilidad
        self.site_name = "doorvel"
        self.normalizer = DataNormalizer()

    # ---------- API pública (consumida por _event_generator_listing) ----------

    async def extraer_todas_las_propiedades(self, callback=None, max_pages: int = 0) -> List[Dict[str, Any]]:
        async with aiohttp.ClientSession(headers=self.DEFAULT_HEADERS) as session:
            # 1) Listado por coordenadas (todas las propiedades del área de Mazatlán)
            crudas = await self._listado_por_coordenadas(session)
            # 2) Quedarse solo con terrenos
            terrenos = [c for c in crudas if (c.get("property_type_slug") or "") in SLUGS_TERRENO]

            # 3) Enriquecer cada terreno con su ficha de detalle (en paralelo)
            sem = asyncio.Semaphore(CONCURRENCIA_DETALLE)

            async def _procesar(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
                async with sem:
                    detalle = await self._detalle(session, item.get("id"))
                return self._mapear(item, detalle)

            propiedades = await asyncio.gather(*[_procesar(t) for t in terrenos])
            propiedades = [p for p in propiedades if p]

            # 4) Guardar JSON local de cada propiedad
            for prop in propiedades:
                try:
                    with open(self.json_dir / f"{self.site_name}_{prop['property_id']}.json",
                              "w", encoding="utf-8") as f:
                        json.dump(prop, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

            return propiedades

    # ---------- Endpoints ----------

    async def _listado_por_coordenadas(self, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        params = {
            "place_id": MAZATLAN_PLACE_ID,
            "place_name": MAZATLAN_PLACE_NAME,
            "fallback_bounds": json.dumps(MAZATLAN_BOUNDS, separators=(",", ":")),
        }
        try:
            async with session.get(f"{API}/properties-by-coordinates", params=params,
                                   timeout=aiohttp.ClientTimeout(total=45)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
        except Exception:
            return []
        return data.get("data") or []

    async def _detalle(self, session: aiohttp.ClientSession, pid: Any) -> Optional[Dict[str, Any]]:
        if not pid:
            return None
        try:
            async with session.get(f"{API}/properties/{pid}",
                                   timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        except Exception:
            return None
        return data.get("data") or None

    # ---------- Mapeo ----------

    def _mapear(self, item: Dict[str, Any], detalle: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        try:
            pid = item.get("id") or (detalle or {}).get("id")
            if not pid:
                return None
            d = detalle or {}

            # Precio: MXN principal + USD aparte
            precio = None
            moneda = "MXN"
            mxn = self._num(d.get("price_mxn") or (item.get("currency") == "MXN" and item.get("price")))
            if mxn:
                precio = f"${mxn:,} MXN"
            usd = self._num(d.get("price_usd"))
            precio_usd = f"${usd:,} USD" if usd else None
            if not precio and usd:
                precio, moneda = precio_usd, "USD"

            # Ubicación
            loc = d.get("location") or {}
            ubic_partes = [loc.get("street"), loc.get("city"), loc.get("state")]
            ubicacion = ", ".join(p for p in ubic_partes if p) or item.get("string_location") or "Mazatlán, Sinaloa"

            coordenadas: Dict[str, Any] = {}
            lat = loc.get("lat") or item.get("lat")
            lon = loc.get("lon") or item.get("lon")
            try:
                if lat and lon:
                    coordenadas = {"lat": float(lat), "lng": float(lon)}
            except (ValueError, TypeError):
                coordenadas = {}

            # Superficie del terreno: additionals.square_meters_ground o, si es 0,
            # se intenta extraer de la descripción ("... 401.42 m² ...").
            terreno: Dict[str, Any] = {}
            caracteristicas: Dict[str, Any] = {}
            adic = d.get("additionals") or {}
            sup = self._num_float(adic.get("square_meters_ground")) or self._num_float(item.get("square_meters_ground"))
            descripcion = (d.get("description") or "").strip() or None
            if not sup and descripcion:
                m = re.search(r'([\d.,]+)\s*m[²2]\b', descripcion)
                if m:
                    sup = self._num_float(m.group(1))
            if sup:
                terreno["superficie_m2"] = sup
                caracteristicas["superficie_m2"] = sup

            amen = d.get("amenities")
            if isinstance(amen, dict) and amen:
                caracteristicas["amenidades"] = list(amen.values())

            # Imágenes
            fotos = d.get("photos") or []
            if not fotos and d.get("primary_photo"):
                fotos = [d["primary_photo"]]
            imagenes = [f for f in fotos if isinstance(f, str) and f.startswith("http")]

            # URL de detalle
            url = d.get("url") or (f"{WEB}{d['path']}" if d.get("path") else
                                   f"{WEB}/business/propiedades/{item.get('path_url_complete', '')}")

            # Agente / equipo
            agente = {}
            ag = d.get("agent") or d.get("team_owner") or {}
            if isinstance(ag, dict) and ag:
                nombre = ag.get("name") or ag.get("full_name") or ag.get("business_name")
                if nombre:
                    agente["nombre"] = nombre

            titulo = (d.get("title") or "").strip() or f"Terreno en venta en {loc.get('city') or 'Mazatlán'}"

            return {
                "url": url,
                "site": self.site_name,
                "property_id": str(pid),
                "empresa": "Doorvel",
                "titulo": titulo,
                "ubicacion": ubicacion,
                "zona": loc.get("county") or loc.get("city"),
                "precio": precio,
                "precio_usd": precio_usd,
                "precio_normalizado": self.normalizer.normalizar_precio(precio) if precio else None,
                "moneda": moneda,
                "estado": "En venta",
                "tipo_propiedad": "terreno",
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
    def _num(valor: Any) -> Optional[int]:
        if valor in (None, "", 0, "0", "0.00"):
            return None
        m = re.search(r'([\d,]+)', str(valor).split(".")[0])
        if not m:
            return None
        try:
            n = int(m.group(1).replace(",", ""))
            return n or None
        except ValueError:
            return None

    @staticmethod
    def _num_float(valor: Any) -> Optional[float]:
        if valor in (None, "", 0, "0", "0.00", "0.0"):
            return None
        try:
            f = float(str(valor).replace(",", ""))
            return round(f, 2) if f > 0 else None
        except (ValueError, TypeError):
            return None


async def main():
    """Prueba rápida del scraper."""
    scraper = DoorvelScraper(output_dir="data")
    props = await scraper.extraer_todas_las_propiedades()
    print(f"\n✅ {len(props)} terrenos extraídos")
    cp = [p for p in props if p["precio"]]
    cd = [p for p in props if p.get("descripcion")]
    cm = [p for p in props if p.get("terreno", {}).get("superficie_m2")]
    ci = [p for p in props if p["imagenes"]]
    print(f"con precio: {len(cp)} | con descripción: {len(cd)} | con m²: {len(cm)} | con imágenes: {len(ci)}")
    if props:
        p = props[0]
        print(json.dumps({k: p[k] for k in ("titulo", "precio", "precio_usd", "ubicacion", "terreno",
                                            "coordenadas", "property_id", "url")},
                         indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
