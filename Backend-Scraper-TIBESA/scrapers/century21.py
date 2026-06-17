"""
Scraper para Century 21 México (https://century21mexico.com)

La plataforma (Viviendi) renderiza los resultados en cliente, PERO expone la
misma URL de búsqueda como API JSON añadiendo `?json=true`. Eso devuelve los
resultados ya filtrados (100% Mazatlán) en JSON, así que se scrapea con **HTTP
puro (aiohttp), sin Playwright ni anti-bot** — como Casas y Terrenos.

Notas:
- La estructura de URL vieja `/busqueda/...` está deprecada (410 Gone). La
  vigente es `/v/resultados/operacion_venta/en-pais_mexico/en-estado_sinaloa/
  en-municipio_mazatlan`.
- Paginación por PATH: `.../pagina_N?json=true` (los params ?pagina/?page se
  ignoran). 100 resultados por página; `totalHits` indica el total.
- El listado trae todo menos la descripción de texto libre; esa se toma de la
  ficha de detalle `/propiedad/{slug}?json=true` (campo `entity.descripcion`),
  enriqueciendo cada propiedad en paralelo.
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from utils.data_normalizer import DataNormalizer

BASE = "https://century21mexico.com"
LISTADO_PATH = ("/v/resultados/operacion_venta/en-pais_mexico/"
                "en-estado_sinaloa/en-municipio_mazatlan")

CONCURRENCIA_DETALLE = 10
REINTENTOS_DETALLE = 3
RESULTADOS_POR_PAGINA = 100
MAX_PAGINAS = 30  # tope de seguridad


class Century21Scraper:
    """Scraper de listado (HTTP plano + API ?json=true) para Century 21 México."""

    LISTADO_URL = f"{BASE}{LISTADO_PATH}"

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json,text/plain,*/*",
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

    # ---------- API pública (consumida por _event_generator_listing) ----------

    async def extraer_todas_las_propiedades(self, callback=None, max_pages: int = 0) -> List[Dict[str, Any]]:
        async with aiohttp.ClientSession(headers=self.DEFAULT_HEADERS) as session:
            # 1) Recorrer páginas de la API hasta cubrir totalHits
            crudas: List[Dict[str, Any]] = []
            total_hits = None
            pagina = 1
            tope = max_pages or MAX_PAGINAS
            while pagina <= tope:
                data = await self._pedir_pagina(session, pagina)
                if not data:
                    break
                if total_hits is None:
                    try:
                        total_hits = int(data.get("totalHits") or 0)
                    except (ValueError, TypeError):
                        total_hits = 0
                resultados = data.get("results") or []
                if not resultados:
                    break
                crudas.extend(resultados)
                if total_hits and len(crudas) >= total_hits:
                    break
                if len(resultados) < RESULTADOS_POR_PAGINA:
                    break
                pagina += 1

            propiedades = [self._mapear_propiedad(r) for r in crudas]
            propiedades = [p for p in propiedades if p]

            # 2) Enriquecer con la descripción de la ficha de detalle (en paralelo)
            sem = asyncio.Semaphore(CONCURRENCIA_DETALLE)

            async def _enriquecer(prop: Dict[str, Any]):
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

    # ---------- Listado (API ?json=true) ----------

    async def _pedir_pagina(self, session: aiohttp.ClientSession, pagina: int) -> Optional[Dict[str, Any]]:
        path = self.LISTADO_URL if pagina == 1 else f"{self.LISTADO_URL}/pagina_{pagina}"
        url = f"{path}?json=true"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=40)) as resp:
                if resp.status != 200:
                    return None
                return await resp.json(content_type=None)
        except Exception:
            return None

    def _mapear_propiedad(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Mapea un resultado de la API al formato común de los scrapers."""
        try:
            pid = raw.get("id")
            if not pid:
                return None

            canonical = raw.get("urlCorrectaPropiedad") or ""
            url = f"{BASE}{canonical}" if canonical.startswith("/") else canonical

            moneda = raw.get("moneda") or "MXN"
            # Precio: precioFormat ya viene formateado ("$2,600,000 MXN"); respetar ocultarPrecio
            if raw.get("ocultarPrecioInternet"):
                precio = None
            else:
                precio = raw.get("precioFormat") or None
                if precio and "$" not in precio:
                    precio = f"${precio}"

            ubic = ", ".join(p for p in (raw.get("colonia"), raw.get("municipio"), raw.get("estado")) if p)

            # Superficie de terreno (m2T) y construcción (m2C)
            terreno: Dict[str, Any] = {}
            if raw.get("m2T"):
                try:
                    terreno["superficie_m2"] = float(raw["m2T"])
                except (ValueError, TypeError):
                    pass
            if raw.get("m2C"):
                try:
                    terreno["superficie_construida_m2"] = float(raw["m2C"])
                except (ValueError, TypeError):
                    pass

            caracteristicas: Dict[str, Any] = {}
            if terreno.get("superficie_m2"):
                caracteristicas["superficie_m2"] = terreno["superficie_m2"]
            for campo, clave in (("recamaras", "recamaras"), ("banos", "baños"),
                                 ("estacionamientos", "estacionamientos")):
                if raw.get(campo):
                    caracteristicas[clave] = raw[campo]
            if raw.get("alberca"):
                caracteristicas["alberca"] = True

            # Agente / asesor (incluye contacto — útil para leads)
            agente: Dict[str, Any] = {}
            if raw.get("asesorNombre"):
                agente["nombre"] = raw["asesorNombre"]
            for campo, clave in (("telefono", "telefono"), ("whatsapp", "whatsapp"),
                                 ("email", "email"), ("nombreAfiliado", "oficina")):
                if raw.get(campo):
                    agente[clave] = raw[campo]

            imagenes = []
            fotos = raw.get("fotos") or {}
            if isinstance(fotos, dict):
                imagenes = fotos.get("propiedadThumbnail") or []

            coords = {}
            if raw.get("lat") and raw.get("lon"):
                coords = {"lat": raw["lat"], "lng": raw["lon"]}

            return {
                "url": url,
                "site": self.site_name,
                "property_id": str(pid),
                "empresa": raw.get("nombreAfiliado") or "Century 21",
                "titulo": (raw.get("encabezado") or "").strip() or None,
                "ubicacion": ubic or None,
                "precio": precio,
                "precio_normalizado": self.normalizer.normalizar_precio(precio) if precio else None,
                "moneda": moneda,
                "estado": "En venta" if raw.get("tipoOperacion") == "venta" else None,
                "tipo_propiedad": self._normalizar_tipo(raw.get("tipoPropiedad") or raw.get("tipoPropiedadTrans")),
                "terreno": terreno,
                "caracteristicas": caracteristicas,
                "descripcion": None,  # se completa con la ficha de detalle
                "agente": agente,
                "coordenadas": coords,
                "imagenes": imagenes,
                "imagenes_descargadas": [],
            }
        except Exception:
            return None

    # ---------- Detalle (solo para la descripción + amenidades) ----------

    async def _extraer_detalle(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict[str, Any]]:
        if not url:
            return None
        # Reintentos: bajo ráfaga, el servidor rechaza/corta algunas peticiones.
        # Un par de reintentos con backoff recupera casi todas las descripciones.
        data = None
        for intento in range(REINTENTOS_DETALLE):
            try:
                async with session.get(f"{url}?json=true", timeout=aiohttp.ClientTimeout(total=40)) as resp:
                    if resp.status == 404:
                        return None  # ficha inexistente: no insistir
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        break
            except Exception:
                pass
            await asyncio.sleep(1.0 + intento)  # backoff: 1s, 2s, 3s
        if data is None:
            return None

        out: Dict[str, Any] = {}
        entity = data.get("entity") if isinstance(data, dict) else None
        desc = entity.get("descripcion") if isinstance(entity, dict) else None
        if isinstance(desc, str) and desc.strip():
            out["descripcion"] = desc.strip()

        amenities = data.get("amenitiesTxt") if isinstance(data, dict) else None
        if isinstance(amenities, list) and amenities:
            out["caracteristicas"] = {"amenidades": [a for a in amenities if a]}
        elif isinstance(amenities, str) and amenities.strip():
            out["caracteristicas"] = {"amenidades": [amenities.strip()]}
        return out

    # ---------- Utilidades ----------

    @staticmethod
    def _normalizar_tipo(tipo: Optional[str]) -> Optional[str]:
        t = (tipo or "").lower()
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
