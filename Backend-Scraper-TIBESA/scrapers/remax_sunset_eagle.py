"""
Scraper específico para RE/MAX Sunset Eagle - Mazatlán
https://es.remaxsunseteagle.com/

Sitio con HTML server-side (Laravel + Alpine, detrás de Cloudflare sin reto):
no requiere Playwright. Usa aiohttp + regex.

Desde ~nov-2026 el sitio se rediseñó (antes /busqueda/.../region:N/ y fichas
/ver-propiedad/<slug>-<id>/, ahora dan 404):
  Listado:          /propiedades?page=<P>   (12 por página; la tarjeta trae
                    "Tipo · Colonia · Zona", con eso se filtra por zona)
  Ficha:            /propiedades/<slug>
  Datos de la ficha: JSON-LD Product (precio, moneda, MLS, imagen) +
  window.__chatPageContext (tipo, zona, MLS) + bloques HTML (specs, amenidades).
"""

import asyncio
import json
import re
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import aiohttp

from utils.image_downloader import ImageDownloader
from utils.data_normalizer import DataNormalizer


class RemaxSunsetEagleScraper:
    """Scraper para RE/MAX Sunset Eagle (Mazatlán) — descubrimiento por zona + detalle."""

    BASE_URL = "https://es.remaxsunseteagle.com"
    LISTADO_URL = f"{BASE_URL}/propiedades"

    ZONAS: Dict[int, str] = {
        1: "Centro Histórico",
        2: "Malecón",
        3: "Zona Dorada / Sábalo",
        4: "Playa Sur",
        5: "Marina",
        6: "Cerritos",
        7: "Nuevo Mazatlán",
        8: "Este Mazatlán",
    }

    # Palabras con que se reconoce cada zona en la línea "Tipo · Colonia · Zona"
    # de las tarjetas del listado. (El filtro ?zone= de la web no sirve: Playa Sur,
    # Nuevo Mazatlán y Este Mazatlán devuelven 0, y usa otra taxonomía.)
    ZONA_CLAVES: Dict[int, Tuple[str, ...]] = {
        1: ("centro",),
        2: ("malecon", "malecón"),
        3: ("zona dorada", "sabalo", "sábalo", "el cid"),
        4: ("playa sur",),
        5: ("marina",),
        6: ("cerritos",),
        7: ("nuevo mazatl",),
        8: ("este mazatl", "oriente"),
    }

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
    }

    def __init__(
        self,
        output_dir: str = "data",
        descargar_imagenes: bool = True,
        max_imagenes_por_propiedad: int = 1,
        concurrencia: int = 4,
    ):
        self.output_dir = Path(output_dir)
        self.images_dir = self.output_dir / "imagenes"
        self.json_dir = self.output_dir / "json"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.json_dir.mkdir(parents=True, exist_ok=True)

        self.site_name = "remax_sunset_eagle"
        self.descargar_imagenes = descargar_imagenes
        self.max_imagenes_por_propiedad = max_imagenes_por_propiedad
        self.concurrencia = concurrencia

        self.image_downloader = ImageDownloader(str(self.images_dir))
        self.normalizer = DataNormalizer()

    async def _recorrer_listado(self, session: aiohttp.ClientSession) -> List[Tuple[str, str]]:
        """Recorre /propiedades?page=N y devuelve [(url_ficha, meta)], donde meta es
        la línea de la tarjeta "Condominio · Playa Sur · Centro" (tipo · colonia · zona)."""
        items: List[Tuple[str, str]] = []
        seen = set()
        for page in range(1, 101):  # tope de seguridad (12 por página)
            html = await self._fetch(session, f"{self.LISTADO_URL}?page={page}")
            if not html:
                break
            agregadas = 0
            for url, meta in self._extraer_cards_listado(html):
                if url not in seen:
                    seen.add(url)
                    items.append((url, meta))
                    agregadas += 1
            if agregadas == 0:
                break
        return items

    async def discover_urls_todas(self, session: aiohttp.ClientSession) -> List[str]:
        """Todas las propiedades del sitio (la zona de cada una sale luego de su ficha)."""
        return [u for u, _ in await self._recorrer_listado(session)]

    async def discover_urls_por_zona(
        self, session: aiohttp.ClientSession, zona_id: int
    ) -> Tuple[List[str], int]:
        """Propiedades de una zona: listado general filtrado por la línea de la tarjeta."""
        if zona_id not in self.ZONAS:
            raise ValueError(f"Zona {zona_id} inválida. Válidas: {list(self.ZONAS.keys())}")
        claves = self.ZONA_CLAVES[zona_id]
        urls = [
            u for u, meta in await self._recorrer_listado(session)
            if any(c in meta.lower() for c in claves)
        ]
        return urls, len(urls)

    async def extraer_detalle(
        self,
        session: aiohttp.ClientSession,
        url: str,
        zona_nombre: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Extrae datos completos de una ficha /propiedades/{slug}."""
        html = await self._fetch(session, url)
        if not html:
            return None

        prop_id = self._extraer_property_id(url)

        data: Dict[str, Any] = {
            "url": url,
            "site": self.site_name,
            "fecha_scraping": datetime.now().isoformat(),
            "empresa": "RE/MAX Sunset Eagle",
            "property_id": prop_id,
            "zona": zona_nombre,
            "titulo": None,
            "tipo_operacion": None,
            "tipo_propiedad": None,
            "ubicacion": None,
            "direccion_completa": None,
            "codigo": None,
            "precio": None,
            "precio_numerico": None,
            "moneda": None,
            "terreno": {},
            "caracteristicas": {},
            "descripcion": None,
            "agente": {},
            "amenidades": [],
            "imagenes": [],
            "imagenes_descargadas": [],
        }

        ld = self._extraer_jsonld_producto(html)
        ctx = self._extraer_chat_context(html)

        # MLS = identificador estable de la propiedad (el id interno cambió con el rediseño)
        mls = ld.get("sku") or ctx.get("mls")
        if mls:
            data["codigo"] = mls
            data["property_id"] = mls

        m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
        data["titulo"] = self._clean_text(m.group(1)) if m else (ld.get("name") or ctx.get("title"))

        if ctx.get("type"):
            data["tipo_propiedad"] = ctx["type"].strip().lower()
        m = re.search(r'title="MLS">[^<]*</span>\s*<span[^>]*x-text="[^"]*\?\s*\'En (Venta|Renta|Preventa)\'', html)
        if m:
            data["tipo_operacion"] = m.group(1)
        if not data["zona"] and ctx.get("zone"):
            data["zona"] = ctx["zone"].strip()

        # Ubicación corta (badge "Marina, GRAND MARINA…") y dirección completa (bajo el mapa)
        m = re.search(r'title="MLS">.*?<span class="bg-cream[^"]*"[^>]*>(.*?)</span>', html, re.DOTALL)
        if m:
            data["ubicacion"] = self._clean_text(m.group(1))
        m = re.search(r'</iframe>\s*</div>\s*<p class="text-gray-500 text-sm leading-relaxed">(.*?)</p>', html, re.DOTALL)
        if m:
            data["direccion_completa"] = self._clean_text(m.group(1))
            data["ubicacion"] = data["ubicacion"] or data["direccion_completa"]

        # Precio: JSON-LD (numérico + moneda); el texto visible como precio legible
        oferta = ld.get("offers") or {}
        if isinstance(oferta, list):
            oferta = oferta[0] if oferta else {}
        moneda = oferta.get("priceCurrency")
        try:
            data["precio_numerico"] = float(oferta.get("price")) if oferta.get("price") else None
        except (TypeError, ValueError):
            data["precio_numerico"] = None
        data["moneda"] = moneda
        m = re.search(r'<p class="text-2xl font-bold text-primary[^"]*">([^<]+)</p>', html)
        if m:
            data["precio"] = self._clean_text(m.group(1))
        elif data["precio_numerico"]:
            data["precio"] = f"${data['precio_numerico']:,.0f} {moneda or ''}".strip()

        self._extraer_specs(html, data)

        m = re.search(r'<div class="prose[^"]*">(.*?)</div>', html, re.DOTALL)
        if m:
            data["descripcion"] = self._clean_text(m.group(1))
        else:
            data["descripcion"] = ld.get("description")

        data["agente"] = self._extraer_agente(html)
        data["amenidades"] = self._extraer_amenidades(html)

        urls_imgs = self._extraer_urls_imagenes(html, ld)
        data["imagenes"] = urls_imgs[: self.max_imagenes_por_propiedad]
        if self.descargar_imagenes and data["imagenes"] and data["property_id"]:
            data["imagenes_descargadas"] = await self.image_downloader.descargar_multiples(
                data["imagenes"],
                prefijo=self.site_name,
                carpeta_propiedad=f"{self.site_name}_{data['property_id']}",
            )

        return data

    async def scrape_zona(
        self,
        zona_id: int,
        max_props: Optional[int] = None,
        guardar: bool = True,
    ) -> Dict[str, Any]:
        """Scrapea una zona completa: discovery + detalle de todas (o N) propiedades."""
        zona_nombre = self.ZONAS[zona_id]
        print(f"\n{'=' * 80}\n🌎 ZONA {zona_id}: {zona_nombre}\n{'=' * 80}")

        connector = aiohttp.TCPConnector(limit=self.concurrencia)
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(
            headers=self.DEFAULT_HEADERS, connector=connector, timeout=timeout
        ) as session:
            urls, total_reportado = await self.discover_urls_por_zona(session, zona_id)
            print(f"   ✓ {len(urls)} URLs descubiertas (total reportado: {total_reportado})")

            if max_props:
                urls = urls[:max_props]
                print(f"   ⚠ Limitando a {max_props} propiedades para prueba")

            sem = asyncio.Semaphore(self.concurrencia)

            async def _scrape_one(u: str):
                async with sem:
                    print(f"\n   🏠 {u}")
                    try:
                        return await self.extraer_detalle(session, u, zona_nombre)
                    except Exception as e:
                        print(f"      ✗ Error: {e}")
                        return None

            propiedades = await asyncio.gather(*[_scrape_one(u) for u in urls])
            propiedades = [p for p in propiedades if p]

        resultado = {
            "site": self.site_name,
            "zona_id": zona_id,
            "zona_nombre": zona_nombre,
            "total_reportado": total_reportado,
            "total_scrapeadas": len(propiedades),
            "fecha_scraping": datetime.now().isoformat(),
            "propiedades": propiedades,
        }

        if guardar:
            self._guardar_resultado(resultado, zona_id)

        return resultado

    async def _fetch(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        try:
            async with session.get(url, allow_redirects=True) as resp:
                if resp.status != 200:
                    print(f"   ✗ HTTP {resp.status}: {url}")
                    return None
                return await resp.text()
        except Exception as e:
            print(f"   ✗ Fetch error en {url}: {e}")
            return None

    def _extraer_cards_listado(self, html: str) -> List[Tuple[str, str]]:
        cards = []
        for art in re.findall(r"<article\b.*?</article>", html, re.DOTALL):
            m = re.search(r'href="((?:https://es\.remaxsunseteagle\.com)?/propiedades/[a-z0-9-]+)"', art)
            if not m:
                continue
            meta = re.search(r'<p class="text-sm text-gray-500 mb-3">(.*?)</p>', art, re.DOTALL)
            cards.append((urljoin(self.BASE_URL, m.group(1)), self._clean_text(meta.group(1)) if meta else ""))
        return cards

    def _extraer_urls_propiedades_listado(self, html: str) -> List[str]:
        urls = []
        seen = set()
        for m in re.finditer(r'href="((?:https://es\.remaxsunseteagle\.com)?/propiedades/[a-z0-9-]+)"', html):
            u = urljoin(self.BASE_URL, m.group(1))
            if u not in seen:
                seen.add(u)
                urls.append(u)
        return urls

    @staticmethod
    def _extraer_jsonld_producto(html: str) -> Dict[str, Any]:
        for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL):
            try:
                obj = json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("@type") == "Product":
                return obj
        return {}

    @staticmethod
    def _extraer_chat_context(html: str) -> Dict[str, str]:
        """Lee window.__chatPageContext = { title: "...", mls: "...", zone: "...", type: "..." }."""
        m = re.search(r"window\.__chatPageContext\s*=\s*\{(.*?)\};", html, re.DOTALL)
        if not m:
            return {}
        ctx = {}
        for k, v in re.findall(r'(\w+):\s*"((?:[^"\\]|\\.)*)"', m.group(1)):
            try:
                ctx[k] = json.loads(f'"{v}"')  # resuelve escapes \u00e1
            except json.JSONDecodeError:
                ctx[k] = v
        return ctx

    def _extraer_specs(self, html: str, data: Dict[str, Any]):
        """Bloque de iconos: 🛏 recámaras, 🛁 baños, 🏠 m² construcción, 📐 m² lote, 🏢 piso, 🚗 estac."""
        terreno = data.setdefault("terreno", {})
        caract = data.setdefault("caracteristicas", {})
        patron = (
            r'<p class="text-2xl font-bold text-deep"(?:\s+x-text="\$store\.lang\?\.is\(\'es\'\)\s*\?\s*\'([^\']*)\'[^"]*")?>([^<]*)</p>'
            r'\s*<p class="text-xs text-gray-500[^"]*"\s+x-text="\$store\.lang\?\.is\(\'es\'\)\s*\?\s*\'([^\']*)\''
        )
        for valor_es, valor_txt, label in re.findall(patron, html):
            valor = (valor_es or valor_txt).strip()
            num = re.search(r"\d[\d,]*(?:\.\d+)?", valor)
            if not num:
                continue
            n = float(num.group(0).replace(",", ""))
            lab = label.lower()
            if "lote" in lab or "terreno" in lab:
                terreno["superficie_m2"] = n
                terreno["superficie"] = f"{n:g} m²"
            elif "constr" in lab:
                terreno["superficie_construida_m2"] = n
                terreno["superficie_construida"] = f"{n:g} m²"
            elif "rec" in lab:
                caract["recamaras"] = int(n)
            elif "medio" in lab:
                caract["medios_banos"] = int(n)
            elif "baño" in lab or "bano" in lab:
                caract["banos"] = n
            elif "piso" in lab or "nivel" in lab:
                caract["pisos"] = int(n)
            elif "estac" in lab:
                caract["estacionamientos"] = int(n)

    def _extraer_amenidades(self, html: str) -> List[str]:
        i = html.find("'Amenidades' : 'Amenities'")
        if i < 0:
            return []
        fin = html.find("</iframe>", i)
        bloque = html[i: fin if fin > 0 else i + 20000]
        return [
            self._clean_text(t)
            for t in re.findall(r"</svg>\s*<span[^>]*>(.*?)</span>", bloque, re.DOTALL)
            if self._clean_text(t)
        ]

    def _extraer_agente(self, html: str) -> Dict[str, Any]:
        agente: Dict[str, Any] = {}
        m = re.search(
            r'<a href="(https://es\.remaxsunseteagle\.com/agentes/[^"]+)"[^>]*>\s*<img src="([^"]+)"[^>]*>\s*<div>\s*<p[^>]*>([^<]+)</p>',
            html,
        )
        if m:
            agente["perfil_url"] = m.group(1)
            agente["foto"] = urljoin(self.BASE_URL, m.group(2))
            agente["nombre"] = self._clean_text(m.group(3))
        return agente

    def _extraer_urls_imagenes(self, html: str, ld: Dict[str, Any]) -> List[str]:
        imgs = ld.get("image") or []
        if isinstance(imgs, str):
            imgs = [imgs]
        return [urljoin(self.BASE_URL, u) for u in imgs if isinstance(u, str)]

    @staticmethod
    def _extraer_property_id(url: str) -> Optional[str]:
        """Fallback si la ficha no trae MLS: el slug de /propiedades/<slug>."""
        m = re.search(r"/propiedades/([a-z0-9-]+)/?$", url)
        return m.group(1) if m else None

    @staticmethod
    def _clean_text(s: str) -> str:
        s = re.sub(r"<[^>]+>", " ", s)
        s = unescape(s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def _guardar_resultado(self, resultado: Dict[str, Any], zona_id: int):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = resultado["zona_nombre"].lower().replace("/", "-").replace(" ", "_")
        path = self.json_dir / f"{self.site_name}_zona{zona_id}_{slug}_{timestamp}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(resultado, f, indent=2, ensure_ascii=False)
        print(f"\n📁 Datos guardados en: {path}")
