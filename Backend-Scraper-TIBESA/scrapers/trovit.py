"""
Scraper para Trovit (https://casas.trovit.com.mx) — AGREGADOR.

Trovit NO tiene inventario propio: recopila anuncios de otros portales (Lamudi,
Inmuebles24, inmobiliarias, etc.), por lo que puede DUPLICAR propiedades que ya
están en los otros scrapers. El enlace de detalle es un redirect de Trovit hacia
el sitio fuente.

Anti-bot: HTTP plano recibe 401 "Access Denied"; un navegador real (Playwright)
pasa sin reto persistente. Por eso usa Playwright internamente (como Mitula) y se
scrapea del listado (`article.snippet-listing`), 30 por página, paginado
`/terreno-mazatlan/{N}`.
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.async_api import async_playwright

from utils.data_normalizer import DataNormalizer

BASE = "https://casas.trovit.com.mx"
LISTADO_URL = f"{BASE}/terreno-mazatlan"
MAX_PAGINAS = 12


class TrovitScraper:
    """Scraper de listado (Playwright) para el agregador Trovit."""

    LISTADO_URL = LISTADO_URL

    def __init__(self, output_dir: str = "data", headless: bool = True):
        self.output_dir = Path(output_dir)
        self.json_dir = self.output_dir / "json"
        self.images_dir = self.output_dir / "imagenes"
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.site_name = "trovit"
        self.normalizer = DataNormalizer()

    def get_browser_config(self) -> Dict[str, Any]:
        return {
            "headless": self.headless,
            "args": ["--disable-blink-features=AutomationControlled",
                     "--disable-dev-shm-usage", "--no-sandbox"],
        }

    def get_context_config(self) -> Dict[str, Any]:
        return {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
            "locale": "es-MX",
            "timezone_id": "America/Mexico_City",
        }

    # ---------- API pública (consumida por _event_generator_listing) ----------

    async def extraer_todas_las_propiedades(self, callback=None, max_pages: int = 0) -> List[Dict[str, Any]]:
        propiedades: List[Dict[str, Any]] = []
        vistos = set()
        tope = max_pages or MAX_PAGINAS

        async with async_playwright() as p:
            browser = await p.chromium.launch(**self.get_browser_config())
            context = await browser.new_context(**self.get_context_config())
            await context.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
            )
            page = await context.new_page()

            try:
                for num in range(1, tope + 1):
                    url = self.LISTADO_URL if num == 1 else f"{self.LISTADO_URL}/{num}"
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        await page.wait_for_timeout(3500)
                    except Exception:
                        break

                    crudas = await self._extraer_cards(page)
                    nuevas = [c for c in crudas if c.get("data_id") and c["data_id"] not in vistos]
                    if not nuevas:
                        break
                    for c in nuevas:
                        vistos.add(c["data_id"])
                        prop = self._mapear(c)
                        if prop:
                            propiedades.append(prop)
                            # Guardar JSON local
                            try:
                                with open(self.json_dir / f"{self.site_name}_{prop['property_id']}.json",
                                          "w", encoding="utf-8") as f:
                                    json.dump(prop, f, indent=2, ensure_ascii=False)
                            except Exception:
                                pass
                    # Si la página trajo menos de 30, probablemente es la última
                    if len(crudas) < 30:
                        break
                    await page.wait_for_timeout(1500)
            finally:
                await browser.close()

        return propiedades

    async def _extraer_cards(self, page) -> List[Dict[str, Any]]:
        """Extrae los campos crudos de cada `article.snippet-listing`."""
        return await page.evaluate(r"""() => {
            const out = [];
            for (const card of document.querySelectorAll("article.snippet-listing")) {
                const link = card.querySelector("a.js-listing");
                const txt = (sel) => { const e = card.querySelector(sel); return e ? e.textContent.trim().replace(/\s+/g,' ') : null; };
                const imgEl = card.querySelector("img");
                out.push({
                    data_id: card.getAttribute("data-id"),
                    titulo: link ? link.getAttribute("title") : null,
                    href: link ? link.getAttribute("href") : null,
                    precio: txt(".price__actual") || txt(".price"),
                    ubicacion: txt(".address_property-type"),
                    agencia: txt(".date-publisher-wrapper-agency"),
                    fecha: txt(".updated-date"),
                    descripcion: txt(".extended-description-content"),
                    imagen: imgEl ? (imgEl.getAttribute("src") || imgEl.getAttribute("data-src")) : null,
                });
            }
            return out;
        }""")

    def _mapear(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            data_id = raw.get("data_id")
            if not data_id:
                return None

            titulo = (raw.get("titulo") or "").strip() or None

            # Precio + moneda
            precio = None
            moneda = "MXN"
            ptxt = raw.get("precio") or ""
            m = re.search(r'\$\s*([\d,]+)', ptxt)
            if m:
                cur = "USD" if "USD" in ptxt.upper() else ("MXN" if "MXN" in ptxt.upper() else "MXN")
                moneda = cur
                precio = f"${m.group(1)} {cur}"

            # Superficie m² desde título/descripción
            terreno: Dict[str, Any] = {}
            caracteristicas: Dict[str, Any] = {}
            blob = f"{titulo or ''} {raw.get('descripcion') or ''}"
            ms = re.search(r'([\d.,]+)\s*m[²2]\b', blob)
            if ms:
                try:
                    sup = float(ms.group(1).replace(",", ""))
                    terreno["superficie_m2"] = sup
                    caracteristicas["superficie_m2"] = sup
                except ValueError:
                    pass

            # Descripción: limpiar el precio/título repetido del inicio
            descripcion = raw.get("descripcion")
            if isinstance(descripcion, str):
                descripcion = descripcion.strip() or None

            agente = {}
            if raw.get("agencia"):
                agente["oficina"] = raw["agencia"]

            href = raw.get("href") or ""
            # quitar parámetros de tracking del redirect de Trovit
            url = href.split("?")[0] if href else ""

            imagenes = [raw["imagen"]] if raw.get("imagen") and raw["imagen"].startswith("http") else []

            return {
                "url": url,
                "site": self.site_name,
                "property_id": str(data_id),
                "empresa": raw.get("agencia") or "Trovit (agregador)",
                "es_agregador": True,
                "titulo": titulo,
                "ubicacion": raw.get("ubicacion") or "Mazatlán, Sinaloa",
                "precio": precio,
                "precio_normalizado": self.normalizer.normalizar_precio(precio) if precio else None,
                "moneda": moneda,
                "estado": "En venta",
                "tipo_propiedad": "terreno",
                "terreno": terreno,
                "caracteristicas": caracteristicas,
                "descripcion": descripcion,
                "agente": agente,
                "imagenes": imagenes,
                "imagenes_descargadas": [],
            }
        except Exception:
            return None


async def main():
    scraper = TrovitScraper(output_dir="data")
    props = await scraper.extraer_todas_las_propiedades()
    print(f"\n✅ {len(props)} propiedades extraídas")
    sin_p = [p for p in props if not p["precio"]]
    con_d = [p for p in props if p.get("descripcion")]
    print(f"sin precio: {len(sin_p)} | con descripción: {len(con_d)}")
    if props:
        p = props[0]
        print(json.dumps({k: p[k] for k in ("titulo", "precio", "ubicacion", "terreno",
                                            "property_id", "url", "empresa")}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
