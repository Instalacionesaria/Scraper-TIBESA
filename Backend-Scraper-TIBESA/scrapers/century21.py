"""
Scraper para Century 21 México (https://century21mexico.com)

Desde ~jul-2026 el sitio migró de Viviendi a la plataforma **Genioi** (PHP +
Alpine.js, detrás de Cloudflare pero SIN challenge anti-bot). La URL vieja
`/v/resultados/...?json=true` ahora responde 301 a
`/propiedades/mx/sinaloa/mazatlan?listingContractType=Sale` y devuelve HTML
(el truco `?json=true` dejó de existir), por eso el scraper viejo daba 0.

Cómo funciona ahora (HTTP puro, aiohttp, sin Playwright):
- La página de listado SSR trae en su JS el UUID de la zona geográfica
  (`zonaDeLaRuta: "<uuid>"`). Se lee de ahí (con un UUID de respaldo).
- La API pública `/api/public/properties?listingContractType=Sale&
  geographicLocation=<uuid>&page=N&limit=60` devuelve JSON
  `{total, page, pages, properties:[...]}` (MAX_LIMIT de la grilla = 60).
- La ficha `/propiedad/{slug}` trae un JSON-LD (`RealEstateListing` +
  `Accommodation` + `Offer` + `RealEstateAgent`) con la descripción, la
  dirección completa y la oficina (nombre + teléfono); además una tabla
  "Características" (condición, financiamiento, dimensiones...) en el HTML.
- Cloudflare responde 429 si se piden muchas fichas en ráfaga: concurrencia
  baja + pausa compartida con backoff al recibir 429.
- El sitio ya no publica el asesor individual: el contacto es la OFICINA.
"""

import asyncio
import html as html_lib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from utils.data_normalizer import DataNormalizer

BASE = "https://century21mexico.com"
LISTADO_PATH = "/propiedades/mx/sinaloa/mazatlan"
LISTADO_QUERY = "listingContractType=Sale"
API_PATH = "/api/public/properties"
# UUID de "México > Sinaloa > Mazatlán" (respaldo si no se puede leer del HTML)
ZONA_MAZATLAN_FALLBACK = "019d5040-7d9b-7184-863c-c34e8f379609"

CONCURRENCIA_DETALLE = 5
REINTENTOS_DETALLE = 6
# Cloudflare limita la ráfaga de fichas con HTTP 429 (sin Retry-After). Al
# recibir uno, TODOS los workers pausan esta base de segundos (x intento).
PAUSA_429_SEG = 10.0
RESULTADOS_POR_PAGINA = 60  # MAX_LIMIT de la API para la grilla
MAX_PAGINAS = 30  # tope de seguridad

_TIPOS_EN = {
    "residential_lot": "terreno", "commercial_lot": "terreno", "land": "terreno",
    "lot": "terreno", "farm": "rancho", "ranch": "rancho",
    "house": "casa", "duplex": "casa", "townhouse": "casa", "villa": "casa",
    "apartment": "departamento", "penthouse": "departamento", "loft": "departamento",
    "studio": "departamento", "condo": "condominio", "condominium": "condominio",
    "retail": "local", "store": "local", "office": "oficina",
    "warehouse": "bodega", "industrial": "bodega", "building": "edificio",
    "productive_property": "rancho",
}


class Century21Scraper:
    """Scraper de listado (HTTP plano + API pública Genioi) para Century 21 México."""

    LISTADO_URL = f"{BASE}{LISTADO_PATH}?{LISTADO_QUERY}"

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
    }

    def __init__(self, output_dir: str = "data", headless: bool = True):
        self.output_dir = Path(output_dir)
        self.json_dir = self.output_dir / "json"
        self.images_dir = self.output_dir / "imagenes"
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless  # no se usa (sin navegador); compatibilidad
        self.site_name = "century21"
        self.normalizer = DataNormalizer()
        self._pausa_hasta = 0.0  # cooldown compartido tras un 429

    # ---------- API pública (consumida por _event_generator_listing) ----------

    async def extraer_todas_las_propiedades(self, callback=None, max_pages: int = 0) -> List[Dict[str, Any]]:
        async with aiohttp.ClientSession(headers=self.DEFAULT_HEADERS) as session:
            # 1) Zona geográfica + recorrer páginas de la API hasta cubrir `pages`
            zona = await self._obtener_zona(session)
            crudas: List[Dict[str, Any]] = []
            vistos = set()
            pagina = 1
            tope = max_pages or MAX_PAGINAS
            total_paginas = None
            while pagina <= tope:
                data = await self._pedir_pagina(session, zona, pagina)
                if not data:
                    break
                if total_paginas is None:
                    try:
                        total_paginas = int(data.get("pages") or 0)
                    except (ValueError, TypeError):
                        total_paginas = 0
                resultados = data.get("properties") or []
                if not resultados:
                    break
                for r in resultados:
                    clave = r.get("id") or r.get("slug")
                    if clave and clave not in vistos:
                        vistos.add(clave)
                        crudas.append(r)
                if total_paginas and pagina >= total_paginas:
                    break
                if len(resultados) < RESULTADOS_POR_PAGINA:
                    break
                pagina += 1

            propiedades = [self._mapear_propiedad(r) for r in crudas]
            propiedades = [p for p in propiedades if p]

            # 2) Enriquecer con la ficha de detalle (en paralelo)
            sem = asyncio.Semaphore(CONCURRENCIA_DETALLE)

            async def _enriquecer(prop: Dict[str, Any]):
                async with sem:
                    detalle = await self._extraer_detalle(session, prop["url"])
                    if not detalle:
                        return
                    if detalle.get("descripcion"):
                        prop["descripcion"] = detalle["descripcion"]
                    if detalle.get("caracteristicas"):
                        prop["caracteristicas"].update(detalle["caracteristicas"])
                    if detalle.get("agente"):
                        prop["agente"].update(detalle["agente"])
                        if detalle["agente"].get("oficina"):
                            prop["empresa"] = detalle["agente"]["oficina"]
                    if detalle.get("ubicacion"):
                        prop["ubicacion"] = detalle["ubicacion"]
                    if detalle.get("imagenes") and len(detalle["imagenes"]) > len(prop["imagenes"]):
                        prop["imagenes"] = detalle["imagenes"]

            await asyncio.gather(*[_enriquecer(p) for p in propiedades])

            # 3) Guardar JSON local de cada propiedad
            for prop in propiedades:
                json_path = self.json_dir / f"{self.site_name}_{prop['property_id']}.json"
                try:
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump(prop, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

            return propiedades

    # ---------- Listado (API /api/public/properties) ----------

    async def _obtener_zona(self, session: aiohttp.ClientSession) -> str:
        """Lee el UUID de la zona (Mazatlán) del JS de la página de listado."""
        try:
            async with session.get(self.LISTADO_URL, timeout=aiohttp.ClientTimeout(total=40)) as resp:
                if resp.status == 200:
                    texto = await resp.text()
                    m = re.search(r'zonaDeLaRuta\s*:\s*"([0-9a-fA-F-]{36})"', texto)
                    if m:
                        return m.group(1)
        except Exception:
            pass
        return ZONA_MAZATLAN_FALLBACK

    async def _pedir_pagina(self, session: aiohttp.ClientSession, zona: str, pagina: int) -> Optional[Dict[str, Any]]:
        params = {
            "listingContractType": "Sale",
            "geographicLocation": zona,
            "page": str(pagina),
            "limit": str(RESULTADOS_POR_PAGINA),
            "priceCurrency": "MXN",
        }
        for intento in range(3):
            try:
                async with session.get(f"{BASE}{API_PATH}", params=params,
                                       headers={"Accept": "application/json"},
                                       timeout=aiohttp.ClientTimeout(total=40)) as resp:
                    if resp.status == 200:
                        return await resp.json(content_type=None)
                    if resp.status in (400, 404):
                        return None
            except Exception:
                pass
            await asyncio.sleep(1.0 + intento)
        return None

    def _mapear_propiedad(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Mapea un resultado de la API al formato común de los scrapers."""
        try:
            slug = raw.get("slug")
            pid = slug or raw.get("id")
            if not pid:
                return None

            url = f"{BASE}/propiedad/{slug}" if slug else None
            if not url:
                return None

            moneda = raw.get("currency") or "MXN"
            # Precio en la moneda original de la propiedad ("$455,567" + currency)
            precio = raw.get("price") or None
            if not precio and raw.get("priceNum"):
                precio = f"${float(raw['priceNum']):,.0f}"
            if precio:
                if "$" not in precio:
                    precio = f"${precio}"
                if moneda not in precio:
                    precio = f"{precio} {moneda}"

            ruta = [x.strip() for x in (raw.get("geographicLocationPath") or "").split(">") if x.strip()]
            estado_geo = ruta[1] if len(ruta) >= 3 else None
            ubic = ", ".join(p for p in (raw.get("neighborhood"), raw.get("city"), estado_geo) if p)

            # Superficie de terreno (lotArea) y construcción (area)
            terreno: Dict[str, Any] = {}
            if raw.get("lotArea"):
                try:
                    terreno["superficie_m2"] = float(raw["lotArea"])
                except (ValueError, TypeError):
                    pass
            if raw.get("area"):
                try:
                    terreno["superficie_construida_m2"] = float(raw["area"])
                except (ValueError, TypeError):
                    pass

            caracteristicas: Dict[str, Any] = {}
            if terreno.get("superficie_m2"):
                caracteristicas["superficie_m2"] = terreno["superficie_m2"]
            for campo, clave in (("beds", "recamaras"), ("baths", "baños"),
                                 ("parking", "estacionamientos")):
                if raw.get(campo):
                    caracteristicas[clave] = raw[campo]
            if raw.get("address"):
                caracteristicas["direccion"] = raw["address"]

            imagenes = [u for u in (raw.get("photos") or []) if u] or (
                [raw["thumbnail"]] if raw.get("thumbnail") else [])

            coords = {}
            if raw.get("lat") and raw.get("lng"):
                coords = {"lat": raw["lat"], "lng": raw["lng"]}

            return {
                "url": url,
                "site": self.site_name,
                "property_id": str(pid),
                "empresa": "Century 21",  # se reemplaza por la oficina en la ficha
                "titulo": (raw.get("title") or "").strip() or None,
                "ubicacion": ubic or None,
                "precio": precio,
                "precio_normalizado": self.normalizer.normalizar_precio(precio) if precio else None,
                "moneda": moneda,
                "estado": "En venta" if (raw.get("listingContractType") or "").lower() == "sale" else None,
                "tipo_propiedad": self._normalizar_tipo(raw.get("subType") or raw.get("type")),
                "terreno": terreno,
                "caracteristicas": caracteristicas,
                "descripcion": None,  # se completa con la ficha de detalle
                "agente": {},  # se completa con la oficina de la ficha
                "coordenadas": coords,
                "imagenes": imagenes,
                "imagenes_descargadas": [],
            }
        except Exception:
            return None

    # ---------- Detalle (JSON-LD + tabla de características) ----------

    async def _extraer_detalle(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict[str, Any]]:
        if not url:
            return None
        # Reintentos: bajo ráfaga, el servidor rechaza/corta algunas peticiones.
        loop = asyncio.get_running_loop()
        texto = None
        for intento in range(REINTENTOS_DETALLE):
            espera = self._pausa_hasta - loop.time()
            if espera > 0:
                await asyncio.sleep(espera)
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=40)) as resp:
                    if resp.status in (404, 410):
                        return None  # ficha inexistente: no insistir
                    if resp.status == 200:
                        texto = await resp.text()
                        break
                    if resp.status == 429:
                        try:
                            pausa = float(resp.headers.get("Retry-After") or 0)
                        except ValueError:
                            pausa = 0.0
                        pausa = max(pausa, PAUSA_429_SEG * (intento + 1))
                        self._pausa_hasta = max(self._pausa_hasta, loop.time() + pausa)
                        continue
            except Exception:
                pass
            await asyncio.sleep(1.0 + intento)  # backoff: 1s, 2s, 3s...
        if not texto:
            return None

        out: Dict[str, Any] = {}
        nodos: List[Dict[str, Any]] = []
        for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', texto, re.S):
            try:
                d = json.loads(m.group(1))
            except Exception:
                continue
            grafo = d.get("@graph") if isinstance(d, dict) else None
            if isinstance(grafo, list):
                nodos.extend(n for n in grafo if isinstance(n, dict))
            elif isinstance(d, dict):
                nodos.append(d)

        def _tipo(n, t):
            v = n.get("@type")
            return v == t or (isinstance(v, list) and t in v)

        listing = next((n for n in nodos if _tipo(n, "RealEstateListing")), {})
        lugar = next((n for n in nodos if n.get("address") and not _tipo(n, "RealEstateAgent")
                      and str(n.get("@id", "")).endswith("#place")), {})
        oficina = next((n for n in nodos if _tipo(n, "RealEstateAgent")
                        and "/oficina/" in str(n.get("@id", "")) and not n.get("@id", "").endswith("mexico-2#office")), {})

        desc = listing.get("description")
        if isinstance(desc, str) and desc.strip():
            out["descripcion"] = html_lib.unescape(desc.strip())

        imgs = listing.get("image")
        if isinstance(imgs, list) and imgs:
            out["imagenes"] = [i for i in imgs if isinstance(i, str)]

        dirc = lugar.get("address") if isinstance(lugar.get("address"), dict) else {}
        partes = [dirc.get("streetAddress"), dirc.get("addressLocality"), dirc.get("addressRegion")]
        if any(partes):
            out["ubicacion"] = ", ".join(p for p in partes if p)

        agente: Dict[str, Any] = {}
        if oficina.get("name"):
            agente["oficina"] = oficina["name"]
            agente["nombre"] = oficina["name"]
        if oficina.get("telephone"):
            agente["telefono"] = oficina["telephone"]
        if oficina.get("url"):
            agente["url"] = oficina["url"]
        if agente:
            out["agente"] = agente

        caracteristicas: Dict[str, Any] = {}
        if dirc.get("postalCode"):
            caracteristicas["codigo_postal"] = dirc["postalCode"]
        if lugar.get("yearBuilt"):
            caracteristicas["año_construccion"] = lugar["yearBuilt"]
        # Tabla "Características" (pares etiqueta/valor) del HTML
        m = re.search(r'<h[23][^>]*>\s*Características\s*</h[23]>(.*?)<h[23][^>]*>', texto, re.S)
        if m:
            celdas = [html_lib.unescape(re.sub(r"\s+", " ", c)).strip()
                      for c in re.split(r"<[^>]+>", m.group(1))]
            celdas = [c for c in celdas if c]
            detalles = {celdas[i]: celdas[i + 1] for i in range(0, len(celdas) - 1, 2)}
            if detalles:
                caracteristicas["detalles"] = detalles
        if caracteristicas:
            out["caracteristicas"] = caracteristicas
        return out

    # ---------- Utilidades ----------

    @staticmethod
    def _normalizar_tipo(tipo: Optional[str]) -> Optional[str]:
        t = (tipo or "").lower()
        if t in _TIPOS_EN:
            return _TIPOS_EN[t]
        mapa = {
            "terreno": "terreno", "lote": "terreno",
            "casa": "casa", "departamento": "departamento", "depto": "departamento",
            "condominio": "condominio", "local": "local", "oficina": "oficina",
            "bodega": "bodega", "edificio": "edificio", "rancho": "rancho",
        }
        for clave, valor in mapa.items():
            if clave in t:
                return valor
        return t or None


async def main():
    """Prueba rápida del scraper."""
    scraper = Century21Scraper(output_dir="data")
    props = await scraper.extraer_todas_las_propiedades()
    print(f"\n✅ {len(props)} propiedades extraídas")
    if props:
        p = props[0]
        print(json.dumps({k: p[k] for k in ("titulo", "precio", "ubicacion", "tipo_propiedad",
                                            "terreno", "agente", "property_id", "url")},
                         indent=2, ensure_ascii=False))
        print("descripción:", (p.get("descripcion") or "")[:200])
        print("num imágenes:", len(p.get("imagenes", [])))


if __name__ == "__main__":
    asyncio.run(main())
