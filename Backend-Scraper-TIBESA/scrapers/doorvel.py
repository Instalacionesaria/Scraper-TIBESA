"""
Scraper para Doorvel (https://www.doorvel.com) — plataforma inmobiliaria.

Doorvel es un Next.js (App Router con RSC) cuyo listado NO está en el HTML: se
carga vía su API pública `api.doorvel.com`. El sitio responde HTTP 200 plano y la
API no exige autenticación para consultar, así que se scrapea con **HTTP puro
(aiohttp)** golpeando directamente la API (sin navegador), el patrón más rápido.

Flujo (rediseño de Doorvel, nov-2026; descubierto del bundle JS):
1. `GET /properties-by-coordinates` con el **polígono (bounds) de Mazatlán** + place_id
   → devuelve los IDs de TODAS las propiedades del área (~1600). Desde el rediseño
   cada item trae SOLO `id, price, lat, lon` (ya no `property_type_slug`).
2. `POST /filter-properties` con `{"ids": [...]}` (paginado por cursor, máx. 100 por
   página) → ficha resumida de cada propiedad (título, path_url_complete, precio
   MXN/USD, fotos, ubicación, superficie). El tipo se deduce del primer segmento de
   `path_url_complete` ("terrenos/en-venta/mexico/sinaloa/mazatlan/427488"); se
   quedan los terrenos en venta (~124).
3. Detalle: `GET /properties/{id}` de la API quedó detrás de **AWS WAF** (responde
   202 + `x-amzn-waf-action: challenge`, cuerpo vacío), así que la ficha completa
   (descripción, coordenadas exactas, anunciante) se lee de la **página web de
   detalle**, que la trae server-side en el payload RSC de Next.js
   (`{"property":{...}}`, mismo esquema que la API) y en un JSON-LD RealEstateListing.

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

# operation_type_id de Doorvel: 1 = venta, 2 = renta
OPERACION_VENTA = 1

# /filter-properties acepta hasta 100 por página
POR_PAGINA = 100

# Fichas de detalle (páginas web) pedidas en paralelo
CONCURRENCIA_DETALLE = 8


class DoorvelScraper:
    """Scraper de Doorvel vía su API pública (HTTP plano, sin navegador)."""

    LISTADO_URL = f"{WEB}/home/terrenos-en-venta-en-mazatlan-sinaloa-mexico"

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
            # 1) Listado por coordenadas: IDs (+lat/lon) de todo el área de Mazatlán
            crudas = await self._listado_por_coordenadas(session)
            coords = {c.get("id"): c for c in crudas if c.get("id")}
            # 2) Fichas resumidas de esos IDs (el tipo viene en path_url_complete)
            resumidas = await self._filtrar_propiedades(session, list(coords))
            terrenos = []
            for r in resumidas:
                slug_tipo = (r.get("path_url_complete") or "").strip("/").split("/")[0]
                if slug_tipo in SLUGS_TERRENO and r.get("operation_type_id") in (None, OPERACION_VENTA):
                    base = coords.get(r.get("id")) or {}
                    terrenos.append({**r, "lat": base.get("lat"), "lon": base.get("lon")})

            # 3) Enriquecer cada terreno con su ficha de detalle (en paralelo)
            sem = asyncio.Semaphore(CONCURRENCIA_DETALLE)

            async def _procesar(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
                async with sem:
                    detalle = await self._detalle(session, item)
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

    async def _filtrar_propiedades(self, session: aiohttp.ClientSession, ids: List[Any]) -> List[Dict[str, Any]]:
        """POST /filter-properties con los IDs, recorriendo el cursor de paginación."""
        if not ids:
            return []
        resultado: List[Dict[str, Any]] = []
        cursor = None
        for _ in range(200):  # tope de seguridad (~20k propiedades)
            params = {"perPage": POR_PAGINA}
            if cursor:
                params["cursor"] = cursor
            try:
                async with session.post(f"{API}/filter-properties", params=params, json={"ids": ids},
                                        timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status != 200:
                        break
                    data = await resp.json()
            except Exception:
                break
            pagina = data.get("data") or []
            resultado.extend(pagina)
            cursor = (data.get("meta") or {}).get("next_cursor")
            if not cursor or not pagina:
                break
        return resultado

    async def _detalle(self, session: aiohttp.ClientSession, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Ficha completa leída de la página web de detalle (la API /properties/{id}
        está detrás de AWS WAF). Devuelve el objeto `property` embebido por Next.js."""
        path = (item.get("path_url_complete") or "").strip("/")
        if not path:
            return None
        url = f"{WEB}/business/propiedades/{path}"
        html = None
        for intento in range(2):
            try:
                async with session.get(url, headers={"Accept": "text/html,application/xhtml+xml"},
                                       timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        break
                    if resp.status in (404, 410):
                        return None
            except Exception:
                pass
            await asyncio.sleep(1 + intento)
        if not html:
            return None
        return self._extraer_property_html(html)

    @staticmethod
    def _extraer_property_html(html: str) -> Optional[Dict[str, Any]]:
        # Payload RSC de Next.js: self.__next_f.push([1,"..."]) concatenados
        try:
            trozos = re.findall(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', html)
            payload = "".join(json.loads(t) for t in trozos)
        except Exception:
            payload = ""
        prop: Dict[str, Any] = {}
        i = payload.find('{"property":{')
        if i >= 0:
            try:
                prop = json.JSONDecoder().raw_decode(payload, i)[0].get("property") or {}
            except Exception:
                prop = {}

        # La descripción suele venir como referencia RSC ("$4b"); el texto real está
        # en el JSON-LD RealEstateListing (o en la fila "4b:T<len>," del payload).
        desc = prop.get("description")
        if not isinstance(desc, str) or desc.startswith("$"):
            desc = None
            for bloque in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
                try:
                    ld = json.loads(bloque)
                except Exception:
                    continue
                if isinstance(ld, dict) and ld.get("@type") == "RealEstateListing":
                    desc = ld.get("description")
                    if not prop.get("title"):
                        prop["title"] = ld.get("name")
                    break
            if not desc and isinstance(prop.get("description"), str):
                ref = prop["description"][1:]
                m = re.search(r'(?:^|[\n\]}])' + re.escape(ref) + r':T([0-9a-f]+),', payload)
                if m:
                    n = int(m.group(1), 16)
                    desc = payload[m.end():].encode("utf-8")[:n].decode("utf-8", "ignore")
            prop["description"] = desc
        return prop or None

    # ---------- Mapeo ----------

    def _mapear(self, item: Dict[str, Any], detalle: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        try:
            pid = item.get("id") or (detalle or {}).get("id")
            if not pid:
                return None
            # Si la página de detalle falla, se usa la ficha resumida de /filter-properties
            d = detalle or item

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
            if isinstance(amen, dict):
                amen = list(amen.values())
            if isinstance(amen, list) and amen:
                caracteristicas["amenidades"] = [
                    (a.get("name") or a.get("amenity") or str(a)) if isinstance(a, dict) else a for a in amen
                ]

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
                nombre = (ag.get("name") or ag.get("hb_name") or ag.get("full_name")
                          or ag.get("business_name"))
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
