"""
Scraper para Casas y Terrenos (https://www.casasyterrenos.com)

Lo mejor de los sitios evaluados: es un Next.js servido por CloudFront SIN reto
anti-bot (HTTP 200 con petición plana). Los datos vienen embebidos en el JSON
`__NEXT_DATA__` del listado, así que se scrapea con **HTTP puro (aiohttp), sin
Playwright** — el flujo más rápido y robusto (como Mitula, pero con datos
estructurados completos: tipo, superficie, precio, colonia, geo e imágenes).

El listado trae todo menos la descripción de texto libre; esa se toma de la
ficha de detalle (también HTTP plano), enriqueciendo cada propiedad en paralelo.

Para Mazatlán/terrenos los ~60 resultados caben en una sola página (el backend
Meilisearch reporta estimatedTotalHits ≈ 60). El parámetro ?pagina se ignora,
así que no hay paginación para esta búsqueda.
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from utils.data_normalizer import DataNormalizer

BASE = "https://www.casasyterrenos.com"
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)

# Cuántas fichas de detalle se piden en paralelo (HTTP plano, sin anti-bot → holgado)
CONCURRENCIA_DETALLE = 8


class CasasYTerrenosScraper:
    """Scraper de listado (HTTP plano + __NEXT_DATA__) para Casas y Terrenos."""

    LISTADO_URL = f"{BASE}/sinaloa/mazatlan/terrenos/venta"

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
        self.site_name = "casasyterrenos"
        self.normalizer = DataNormalizer()

    # ---------- API pública (consumida por _event_generator_listing) ----------

    async def extraer_todas_las_propiedades(self, callback=None, max_pages: int = 0) -> List[Dict[str, Any]]:
        async with aiohttp.ClientSession(headers=self.DEFAULT_HEADERS) as session:
            # 1) Listado: parsear __NEXT_DATA__ y mapear cada propiedad
            crudas = await self._extraer_listado(session)
            propiedades = [self._mapear_propiedad(p) for p in crudas]
            propiedades = [p for p in propiedades if p]

            # 2) Enriquecer con la descripción de la ficha de detalle (en paralelo)
            sem = asyncio.Semaphore(CONCURRENCIA_DETALLE)

            async def _enriquecer(prop: Dict[str, Any]):
                # La ficha de detalle solo aplica a propiedades individuales (/propiedad/);
                # los desarrollos (/d/) usan otra estructura y se omiten.
                if "/propiedad/" not in prop["url"]:
                    return
                async with sem:
                    detalle = await self._extraer_detalle(session, prop["url"])
                    if detalle:
                        if detalle.get("descripcion"):
                            prop["descripcion"] = detalle["descripcion"]
                        if detalle.get("caracteristicas"):
                            prop["caracteristicas"].update(detalle["caracteristicas"])

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

    # ---------- Listado ----------

    async def _extraer_listado(self, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        """Descarga el listado y devuelve la lista cruda de propiedades del __NEXT_DATA__."""
        async with session.get(self.LISTADO_URL, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            html = await resp.text()
        data = self._parse_next_data(html)
        if not data:
            return []
        try:
            return data["props"]["pageProps"]["initialState"]["propertyData"]["properties"]
        except (KeyError, TypeError):
            return []

    def _mapear_propiedad(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Mapea una propiedad cruda del listado al formato común de los scrapers.

        El listado mezcla dos esquemas: propiedades individuales (`/propiedad/`,
        con name/priceSale/surface numéricos) y desarrollos (`/d/`, con
        developmentName y price/surface como rangos {from,to}). Se soportan ambos.
        """
        try:
            pid = raw.get("id")
            if not pid:
                return None

            es_desarrollo = bool(raw.get("isDevelopment"))

            canonical = raw.get("canonical") or ""
            if not canonical:
                slugs = raw.get("slugs")
                if isinstance(slugs, dict):
                    canonical = slugs.get("canonical") or slugs.get("venta") or ""
                elif isinstance(slugs, str):
                    canonical = slugs
            url = f"{BASE}{canonical}" if canonical.startswith("/") else canonical

            moneda = raw.get("currency") or "MXN"

            # Precio: priceSale (número) en propiedades; price {from,to} en desarrollos
            precio = None
            precio_raw = raw.get("priceSale")
            if not precio_raw and isinstance(raw.get("price"), dict):
                desde = raw["price"].get("from")
                if desde:
                    try:
                        precio = f"Desde ${int(float(desde)):,} {moneda}"
                    except (ValueError, TypeError):
                        pass
            else:
                try:
                    n = int(float(precio_raw or 0))
                    precio = f"${n:,} {moneda}" if n else None
                except (ValueError, TypeError):
                    precio = None

            # Ubicación legible
            ubic_partes = [raw.get("neighborhood"), raw.get("municipality"), raw.get("state")]
            ubicacion = ", ".join(p for p in ubic_partes if p)

            # Superficie / terreno: número en propiedades; {from,to} en desarrollos
            terreno: Dict[str, Any] = {}
            surface = raw.get("surface")
            if isinstance(surface, dict):
                if surface.get("from"):
                    terreno["superficie_m2_desde"] = surface["from"]
                if surface.get("to"):
                    terreno["superficie_m2_hasta"] = surface["to"]
            elif surface:
                try:
                    terreno["superficie_m2"] = float(surface)
                except (ValueError, TypeError):
                    pass

            imagenes = raw.get("images") or ([raw["photoPreview"]] if raw.get("photoPreview") else [])

            caracteristicas: Dict[str, Any] = {}
            if terreno.get("superficie_m2"):
                caracteristicas["superficie_m2"] = terreno["superficie_m2"]
            for campo, clave in (("rooms", "recamaras"), ("bathrooms", "baños"),
                                 ("parkingLots", "estacionamientos")):
                if raw.get(campo):
                    caracteristicas[clave] = raw[campo]
            if es_desarrollo:
                caracteristicas["es_desarrollo"] = True

            titulo = (raw.get("name") or raw.get("developmentName") or "").strip()
            if not titulo:
                # Respaldo: "{Tipo} en venta en {colonia}" cuando el portal no trae nombre
                tipo_txt = (raw.get("type") or "Propiedad").strip()
                lugar = raw.get("neighborhood") or raw.get("municipality") or ""
                titulo = f"{tipo_txt} en venta en {lugar}".strip() if lugar else tipo_txt
            titulo = titulo or None

            return {
                "url": url,
                "site": self.site_name,
                "property_id": str(pid),
                "empresa": "Casas y Terrenos",
                "titulo": titulo,
                "ubicacion": ubicacion or None,
                "precio": precio,
                "precio_normalizado": self.normalizer.normalizar_precio(precio) if precio else None,
                "moneda": moneda,
                "estado": "En venta" if raw.get("isSale") else None,
                "tipo_propiedad": self._normalizar_tipo(raw.get("type")),
                "terreno": terreno,
                "caracteristicas": caracteristicas,
                "descripcion": None,  # se completa con la ficha de detalle
                "agente": {},
                "coordenadas": raw.get("_geo") or {},
                "imagenes": imagenes,
                "imagenes_descargadas": [],
            }
        except Exception:
            return None

    # ---------- Detalle (solo para la descripción + amenidades) ----------

    async def _extraer_detalle(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict[str, Any]]:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text()
        except Exception:
            return None

        data = self._parse_next_data(html)
        if not data:
            return None
        try:
            prop = data["props"]["pageProps"]["property"]
        except (KeyError, TypeError):
            return None

        out: Dict[str, Any] = {}
        desc = prop.get("description")
        if isinstance(desc, str) and desc.strip():
            out["descripcion"] = desc.strip()

        # Amenidades / features → flags de características
        caracteristicas: Dict[str, Any] = {}
        amenidades = []
        for campo in ("features", "generalAmenities"):
            valor = prop.get(campo)
            if isinstance(valor, list):
                for item in valor:
                    if isinstance(item, dict):
                        amenidades.append(item.get("name") or item.get("label") or "")
                    elif isinstance(item, str):
                        amenidades.append(item)
        amenidades = [a for a in amenidades if a]
        if amenidades:
            caracteristicas["amenidades"] = amenidades
        if caracteristicas:
            out["caracteristicas"] = caracteristicas
        return out

    # ---------- Utilidades ----------

    @staticmethod
    def _parse_next_data(html: str) -> Optional[Dict[str, Any]]:
        m = _NEXT_DATA_RE.search(html or "")
        if not m:
            return None
        try:
            return json.loads(m.group(1))
        except Exception:
            return None

    @staticmethod
    def _normalizar_tipo(tipo: Optional[str]) -> Optional[str]:
        t = (tipo or "").lower()
        mapa = {
            "terreno": "terreno", "lote": "terreno",
            "casa": "casa", "departamento": "departamento", "depto": "departamento",
            "local": "local", "oficina": "oficina", "bodega": "bodega",
            "edificio": "edificio", "rancho": "rancho",
        }
        for clave, valor in mapa.items():
            if clave in t:
                return valor
        return t or None


async def main():
    """Prueba rápida del scraper."""
    scraper = CasasYTerrenosScraper(output_dir="data")
    props = await scraper.extraer_todas_las_propiedades()
    print(f"\n✅ {len(props)} propiedades extraídas")
    if props:
        p = props[0]
        print(json.dumps({k: p[k] for k in ("titulo", "precio", "ubicacion", "tipo_propiedad",
                                            "terreno", "property_id", "url")},
                         indent=2, ensure_ascii=False))
        print("descripción:", (p.get("descripcion") or "")[:200])
        print("num imágenes:", len(p.get("imagenes", [])))


if __name__ == "__main__":
    asyncio.run(main())
