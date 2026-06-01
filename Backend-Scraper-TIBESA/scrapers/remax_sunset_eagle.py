"""
Scraper específico para RE/MAX Sunset Eagle - Mazatlán
https://es.remaxsunseteagle.com/

Sitio con HTML estático: no requiere Playwright. Usa aiohttp + regex.
Las propiedades están organizadas en 8 zonas (region:1..8) accesibles via:
  /busqueda/propiedades-mazatlan/region:{N}/
  /busqueda/propiedades-mazatlan/region:{N}/page:{P}/
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
    LISTADO_URL = f"{BASE_URL}/propiedades-mazatlan/"
    BUSQUEDA_URL = f"{BASE_URL}/busqueda/propiedades-mazatlan"

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

    async def discover_urls_por_zona(
        self, session: aiohttp.ClientSession, zona_id: int
    ) -> Tuple[List[str], int]:
        """Recorre todas las páginas de una zona y devuelve (urls_unicas, total_reportado)."""
        if zona_id not in self.ZONAS:
            raise ValueError(f"Zona {zona_id} inválida. Válidas: {list(self.ZONAS.keys())}")

        urls: List[str] = []
        seen = set()
        total = 0
        page = 1
        max_paginas = 100

        while page <= max_paginas:
            url = (
                f"{self.BUSQUEDA_URL}/region:{zona_id}/page:{page}/"
                if page > 1
                else f"{self.BUSQUEDA_URL}/region:{zona_id}/"
            )
            html = await self._fetch(session, url)
            if not html:
                break

            if page == 1:
                m = re.search(r"(\d+)\s*Propiedades encontradas", html)
                if m:
                    total = int(m.group(1))

            agregadas = 0
            for u in self._extraer_urls_propiedades_listado(html):
                if u not in seen:
                    seen.add(u)
                    urls.append(u)
                    agregadas += 1

            if agregadas == 0:
                break
            if total and len(urls) >= total:
                break
            page += 1

        return urls, total

    async def extraer_detalle(
        self,
        session: aiohttp.ClientSession,
        url: str,
        zona_nombre: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Extrae datos completos de una página /ver-propiedad/{slug}/."""
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

        m = re.search(
            r'<h1[^>]*class="[^"]*title-view[^"]*"[^>]*>(.*?)</h1>',
            html, re.DOTALL,
        )
        if m:
            titulo_full = self._clean_text(m.group(1))
            data["titulo"] = titulo_full
            tipo_match = re.search(
                r",\s*([\wáéíóúñÁÉÍÓÚÑ\s]+?)\s+en\s+(Venta|Renta|Preventa)\s*$",
                titulo_full, re.IGNORECASE,
            )
            if tipo_match:
                data["tipo_propiedad"] = tipo_match.group(1).strip().lower()
                data["tipo_operacion"] = tipo_match.group(2).capitalize()

        m = re.search(r'<span\s+class="direccion"[^>]*>(.*?)</span>', html, re.DOTALL)
        if m:
            direccion_raw = self._clean_text(
                re.sub(r"<!--.*?-->", "", m.group(1), flags=re.DOTALL)
            )
            data["direccion_completa"] = direccion_raw
            data["ubicacion"] = direccion_raw

        m = re.search(
            r'<span\s+class="precio"[^>]*>\s*([^<]+?)\s*<span\s+class="dt"[^>]*>([^<]+)</span>',
            html, re.DOTALL,
        )
        if m:
            precio_txt = self._clean_text(m.group(1))
            moneda_txt = self._clean_text(m.group(2))
            data["precio"] = f"{precio_txt} {moneda_txt}".strip()
            normalizado = self.normalizer.normalizar_precio(data["precio"])
            data["precio_numerico"] = normalizado.get("precio_numerico")
            data["moneda"] = normalizado.get("moneda") or (
                "MXN" if "MXN" in moneda_txt or "pesos" in moneda_txt.lower()
                else "USD" if "USD" in moneda_txt or "dól" in moneda_txt.lower()
                else None
            )

        pares = self._extraer_pares_dd_dt(html)
        self._mapear_pares_a_data(pares, data)

        m = re.search(
            r'<div\s+class="descripcion_propiedad"[^>]*>.*?<div\s+class="parrafo"[^>]*>\s*<p[^>]*>(.*?)</p>',
            html, re.DOTALL,
        )
        if m:
            data["descripcion"] = self._clean_text(m.group(1))

        data["agente"] = self._extraer_agente(html)

        m = re.search(r'<ul\s+class="lista_amenidades"[^>]*>(.*?)</ul>', html, re.DOTALL)
        if m:
            data["amenidades"] = [
                self._clean_text(li)
                for li in re.findall(r"<li[^>]*>(.*?)</li>", m.group(1), re.DOTALL)
            ]

        urls_imgs = self._extraer_urls_imagenes(html, prop_id)
        data["imagenes"] = urls_imgs[: self.max_imagenes_por_propiedad]
        if self.descargar_imagenes and data["imagenes"] and prop_id:
            data["imagenes_descargadas"] = await self.image_downloader.descargar_multiples(
                data["imagenes"],
                prefijo=self.site_name,
                carpeta_propiedad=f"{self.site_name}_{prop_id}",
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

    def _extraer_urls_propiedades_listado(self, html: str) -> List[str]:
        urls = []
        seen = set()
        for m in re.finditer(r'href="(/ver-propiedad/[^"]+)"', html):
            u = urljoin(self.BASE_URL, m.group(1))
            if u not in seen:
                seen.add(u)
                urls.append(u)
        return urls

    def _extraer_pares_dd_dt(self, html: str) -> List[Tuple[str, str]]:
        m = re.search(
            r'<div\s+class="info_propiedad"[^>]*>(.*?)</div>\s*<div\s+class="acciones"',
            html, re.DOTALL,
        )
        bloque = m.group(1) if m else html

        tokens: List[Tuple[str, str]] = []
        for tm in re.finditer(r'<span\s+class="(dd|dt)"[^>]*>(.*?)</span>', bloque, re.DOTALL):
            kind = tm.group(1)
            text = self._clean_text(tm.group(2))
            if text:
                tokens.append((kind, text))

        pares: List[Tuple[str, str]] = []
        i = 0
        while i < len(tokens) - 1:
            k1, t1 = tokens[i]
            k2, t2 = tokens[i + 1]
            if k1 == "dd" and k2 == "dt":
                pares.append((t1, t2))
                i += 2
            elif k1 == "dt" and k2 == "dd":
                pares.append((t2, t1))
                i += 2
            else:
                i += 1
        return pares

    def _mapear_pares_a_data(self, pares: List[Tuple[str, str]], data: Dict[str, Any]):
        terreno = data.setdefault("terreno", {})
        caract = data.setdefault("caracteristicas", {})

        for valor, label in pares:
            label_low = label.lower()
            valor_clean = re.sub(r"<[^>]+>", "", valor).strip()

            if "código" in label_low or "codigo" in label_low:
                data["codigo"] = valor_clean
            elif label_low.startswith("m2") or "m²" in label_low:
                num = re.search(r"\d[\d,]*(?:\.\d+)?", valor_clean)
                if num:
                    n = float(num.group(0).replace(",", ""))
                    if "lote" in valor_clean.lower():
                        terreno["superficie_m2"] = n
                        terreno["superficie"] = f"{n:g} m²"
                    elif "constr" in valor_clean.lower():
                        terreno["superficie_construida_m2"] = n
                        terreno["superficie_construida"] = f"{n:g} m²"
                    else:
                        terreno.setdefault("superficie_m2", n)
            elif "recámara" in label_low or "recamara" in label_low:
                num = re.search(r"\d+", valor_clean)
                if num:
                    caract["recamaras"] = int(num.group(0))
            elif "medio baño" in label_low or "medio bano" in label_low:
                num = re.search(r"\d+", valor_clean)
                if num:
                    caract["medios_banos"] = int(num.group(0))
            elif "baño" in label_low or "bano" in label_low:
                num = re.search(r"[\d.]+", valor_clean)
                if num:
                    caract["banos"] = float(num.group(0))
            elif "piso" in label_low:
                num = re.search(r"\d+", valor_clean)
                if num:
                    caract["pisos"] = int(num.group(0))
            elif "vista" in label_low:
                caract["vista"] = valor_clean
            elif "estacionamiento" in label_low or "cocheras" in label_low:
                num = re.search(r"\d+", valor_clean)
                if num:
                    caract["estacionamientos"] = int(num.group(0))

    def _extraer_agente(self, html: str) -> Dict[str, Any]:
        agente: Dict[str, Any] = {}

        bloque_match = re.search(
            r'<h3[^>]*>Asociado encargado[^<]*</h3>(.*?)(?=<div\s+class="bloque-info"|</section>)',
            html, re.DOTALL,
        )
        if not bloque_match:
            return agente
        bloque = bloque_match.group(1)

        m = re.search(r'<span\s+class="nombre-agente"[^>]*>([^<]+)</span>', bloque)
        if m:
            agente["nombre"] = self._clean_text(m.group(1))

        m = re.search(r'<img[^>]*src="([^"]+)"', bloque)
        if m:
            agente["foto"] = urljoin(self.BASE_URL, m.group(1))

        # Email: buscar cualquier patrón de email dentro del bloque del agente
        email_match = re.search(r"[\w._%+-]+@[\w.-]+\.[A-Za-z]{2,}", bloque)
        if email_match:
            agente["email"] = email_match.group(0)

        m = re.search(r'href="(/listado_propiedades/agente:[^"]+)"', bloque)
        if m:
            agente["perfil_url"] = urljoin(self.BASE_URL, m.group(1))

        return agente

    def _extraer_urls_imagenes(self, html: str, prop_id: Optional[str]) -> List[str]:
        if prop_id:
            patron = rf'/files/Propiedad/{re.escape(prop_id)}/Foto/view/(\d+)-(\d+)\.(jpg|jpeg|png|webp)'
        else:
            patron = r'/files/Propiedad/\d+/Foto/view/(\d+)-(\d+)\.(jpg|jpeg|png|webp)'

        encontrados = []
        seen = set()
        for m in re.finditer(patron, html, re.IGNORECASE):
            full = m.group(0)
            if full not in seen:
                seen.add(full)
                idx = int(m.group(1))
                encontrados.append((idx, urljoin(self.BASE_URL, full)))

        encontrados.sort(key=lambda x: x[0])
        return [u for _, u in encontrados]

    @staticmethod
    def _extraer_property_id(url: str) -> Optional[str]:
        m = re.search(r"/ver-propiedad/.+?-(\d+)/?$", url)
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
