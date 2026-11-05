"""
Scraper para NocNok (https://inmuebles.nocnok.com) — portal inmobiliario.

En nov-2026 NocNok rehizo el sitio: pasó de Next.js a **SvelteKit**. Se eliminaron
la API `/api/properties/search` (ahora 404) y las rutas `/s/...` (404). El listado
vive ahora en `/categoria/terreno-en-venta/sinaloa/mazatlan` y SvelteKit expone los
datos de cada ruta como JSON en `<ruta>/__data.json` (formato "devalue": arreglo
plano con referencias por índice), sin autenticación ni anti-bot → seguimos con
**HTTP puro (aiohttp)**, sin navegador.

Flujo:
  1. Listado: `/categoria/terreno-en-venta/sinaloa/mazatlan/__data.json?pagina=N`
     → `results` = {page, pageSize (20), total, totalPages, items[]}. Cada tarjeta
     trae código, título, precio+moneda, lotSize (m²), ubicación, lat/lon y fotos.
  2. Detalle (en paralelo): `/propiedad/x/x/x/x-id-<codigo>/__data.json` (el slug
     es libre, sólo importa el código) → descripción, URL canónica y fotos grandes.
     La respuesta es NDJSON (1ª línea = datos; las siguientes son "chunks" de
     promesas que no usamos).
"""

import asyncio
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from utils.data_normalizer import DataNormalizer

BASE = "https://inmuebles.nocnok.com"
LISTADO_PATH = "/categoria/terreno-en-venta/sinaloa/mazatlan"
MAX_PAGINAS = 30
CONCURRENCIA_DETALLE = 3   # el origen responde 429 si se le pega más fuerte
REINTENTOS = 5
BACKOFF_BASE = 1.0         # s; 1, 2, 4, 8, 16


def _devalue(data: List[Any]) -> Any:
    """Decodifica el formato 'devalue' de SvelteKit (arreglo plano con índices)."""
    cache: Dict[int, Any] = {}

    def h(i: Any) -> Any:
        if not isinstance(i, int) or i < 0:
            return None  # -1 undefined, -2 hueco, -3 NaN, etc.
        if i in cache:
            return cache[i]
        v = data[i]
        if isinstance(v, dict):
            out: Dict[str, Any] = {}
            cache[i] = out
            for k, idx in v.items():
                out[k] = h(idx)
            return out
        if isinstance(v, list):
            if v and isinstance(v[0], str):
                # Tipos especiales: ["Date", iso], ["Promise", id], ["Set", ...]...
                out_t = v[1] if v[0] == "Date" and len(v) > 1 else None
                cache[i] = out_t
                return out_t
            lst: List[Any] = []
            cache[i] = lst
            lst.extend(h(x) for x in v)
            return lst
        cache[i] = v
        return v

    return h(0)


def _nodo_datos(texto: str) -> Optional[Dict[str, Any]]:
    """Del __data.json (posible NDJSON) devuelve los datos de la página (último nodo 'data')."""
    linea = texto.split("\n", 1)[0].strip()
    if not linea:
        return None
    d = json.loads(linea)
    if d.get("type") != "data":
        return None
    nodos = [n for n in (d.get("nodes") or []) if n and n.get("type") == "data"]
    if not nodos:
        return None
    return _devalue(nodos[-1]["data"])


class NocNokScraper:
    """Scraper de NocNok vía los __data.json de SvelteKit (HTTP plano, sin navegador)."""

    LISTADO_URL = f"{BASE}{LISTADO_PATH}"

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
        tope = max_pages or MAX_PAGINAS
        tarjetas: List[Dict[str, Any]] = []
        vistos = set()

        async with aiohttp.ClientSession(headers=self.DEFAULT_HEADERS) as session:
            # 1) Listado paginado
            for num in range(1, tope + 1):
                results = await self._buscar_pagina(session, num)
                if not results:
                    break
                items = [it for it in (results.get("items") or []) if isinstance(it, dict)]
                if not items:
                    break
                for it in items:
                    code = it.get("code")
                    if code and code not in vistos:
                        vistos.add(code)
                        tarjetas.append(it)
                total_pag = results.get("totalPages") or 0
                total = results.get("total") or 0
                if (total_pag and num >= total_pag) or (total and len(vistos) >= total):
                    break

            # 2) Detalle (descripción + URL canónica) en paralelo
            sem = asyncio.Semaphore(CONCURRENCIA_DETALLE)

            async def con_detalle(it: Dict[str, Any]):
                async with sem:
                    return it, await self._detalle(session, it)

            pares = await asyncio.gather(*(con_detalle(it) for it in tarjetas))

        propiedades: List[Dict[str, Any]] = []
        for it, det in pares:
            prop = self._mapear(it, det or {})
            if not prop:
                continue
            propiedades.append(prop)
            try:
                with open(self.json_dir / f"{self.site_name}_{prop['property_id']}.json",
                          "w", encoding="utf-8") as f:
                    json.dump(prop, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

        return propiedades

    async def _get_datos(self, session: aiohttp.ClientSession, url: str,
                         params: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
        redirecciones = 0
        intento = 0
        while True:
            try:
                async with session.get(url, params=params,
                                       timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    status = resp.status
                    texto = await resp.text() if status == 200 else ""
            except Exception:
                status, texto = 0, ""

            # 429 = rate limit del origen (detrás de Cloudflare); también reintenta errores de red
            if status in (0, 429, 502, 503, 504):
                intento += 1
                if intento > REINTENTOS:
                    return None
                await asyncio.sleep(BACKOFF_BASE * (2 ** (intento - 1)))
                continue
            if status != 200:
                return None
            try:
                primera = json.loads(texto.split("\n", 1)[0] or "{}")
                # SvelteKit responde {"type":"redirect"} si el slug no es el canónico
                if primera.get("type") == "redirect" and primera.get("location") and redirecciones < 3:
                    redirecciones += 1
                    loc = primera["location"].split("?", 1)[0].rstrip("/")
                    url = (loc if loc.startswith("http") else f"{BASE}{loc}") + "/__data.json"
                    params = None
                    continue
                return _nodo_datos(texto)
            except Exception:
                return None

    async def _buscar_pagina(self, session: aiohttp.ClientSession, num: int) -> Optional[Dict[str, Any]]:
        datos = await self._get_datos(session, f"{self.LISTADO_URL}/__data.json",
                                      params={"pagina": str(num)} if num > 1 else None)
        res = (datos or {}).get("results")
        return res if isinstance(res, dict) else None

    async def _detalle(self, session: aiohttp.ClientSession, it: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # El sitio resuelve por el código tras "-id-"; el slug canónico es la colonia.
        # Si no coincide, SvelteKit devuelve un redirect que _get_datos sigue.
        return await self._get_datos(session, self._url_ficha(it) + "/__data.json")

    @staticmethod
    def _slug(texto: Any) -> str:
        t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-") or "p"

    def _url_ficha(self, it: Dict[str, Any]) -> str:
        code = str(it.get("code") or "").lower()
        return f"{BASE}/propiedad/terreno-en-venta/sinaloa/mazatlan/{self._slug(it.get('settlement'))}-id-{code}"

    # ---------- Mapeo ----------

    def _mapear(self, it: Dict[str, Any], det: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            pid = it.get("code") or it.get("publicId")
            if not pid:
                return None
            full = det.get("property") if isinstance(det.get("property"), dict) else {}

            titulo = (it.get("title") or full.get("title") or "").strip() or None

            # Precio + moneda (operación de venta)
            precio = None
            moneda = "MXN"
            ops = it.get("operations") or full.get("operations") or []
            op = next((o for o in ops if isinstance(o, dict) and o.get("operation") == "Sale"),
                      ops[0] if ops else None)
            if isinstance(op, dict) and op.get("price"):
                moneda = (op.get("currencyCode") or "MXN").upper()
                try:
                    precio = f"${float(op['price']):,.0f} {moneda}"
                except (ValueError, TypeError):
                    precio = None

            # Superficie del terreno (m²)
            terreno: Dict[str, Any] = {}
            caracteristicas: Dict[str, Any] = {}
            sup = self._m2(it.get("lotSize")) or self._m2(it.get("constructionSize"))
            if sup:
                terreno["superficie_m2"] = sup
                caracteristicas["superficie_m2"] = sup

            # Coordenadas
            coordenadas: Dict[str, Any] = {}
            lat = it.get("lat") if it.get("lat") is not None else full.get("lat")
            lon = it.get("lon") if it.get("lon") is not None else full.get("lon")
            try:
                if lat and lon:
                    coordenadas = {"lat": float(lat), "lng": float(lon)}
            except (ValueError, TypeError):
                coordenadas = {}

            # Fotos: grandes del detalle si existen; si no, las de la tarjeta
            imagenes = [ph.get("large") for ph in (full.get("photos") or [])
                        if isinstance(ph, dict) and isinstance(ph.get("large"), str)
                        and ph["large"].startswith("http")]
            if not imagenes:
                imagenes = [u for u in (it.get("photoUrls") or [])
                            if isinstance(u, str) and u.startswith("http")]

            canon = det.get("canonical")
            if isinstance(canon, str) and canon:
                url = canon if canon.startswith("http") else f"{BASE}{canon}"
            else:
                url = self._url_ficha(it)

            return {
                "url": url,
                "site": self.site_name,
                "property_id": str(pid),
                "empresa": "NocNok",
                "titulo": titulo,
                "ubicacion": it.get("location") or full.get("location") or "Mazatlán, Sinaloa",
                "precio": precio,
                "precio_normalizado": self.normalizer.normalizar_precio(precio) if precio else None,
                "moneda": moneda,
                "estado": "En venta",
                "tipo_propiedad": "terreno",
                "terreno": terreno,
                "caracteristicas": caracteristicas,
                "descripcion": (full.get("description") or "").strip() or None,
                "agente": {},
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
