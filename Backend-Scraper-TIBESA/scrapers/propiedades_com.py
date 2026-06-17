"""
Scraper específico para Propiedades.com (portal nacional)
https://propiedades.com

Particularidades:
- Protegido por **Akamai Bot Manager** (cookies _abck, bm_sz, ak_bmsc, sec_cpt…).
  HTTP plano no conecta (curl da HTTP 000). Un navegador real (Playwright) recibe
  primero una página "Challenge Validation" y el contenido real aparece tras
  recargar. Por eso heredamos de BaseScraper (Playwright) y sobreescribimos
  `wait_for_page_load` para resolver el reto recargando hasta que cargue.
  Nota: las cookies del challenge persisten en el contexto, así que en el flujo
  de detalle (un solo navegador compartido) solo la primera página paga el costo.
- Cada ficha trae JSON-LD: `Apartment` (address, name, description) + `Offer`
  (price, priceCurrency). La descripción rica está en `.description-text`.
- Filtro por ciudad va en la URL del listado (aquí: Mazatlán, terrenos).
"""

import json
import re
from typing import Dict, Any, List
from urllib.parse import urljoin
from playwright.async_api import Page

from .base_scraper import BaseScraper
from utils.data_normalizer import DataNormalizer


# Títulos de la página de reto de Akamai (no son contenido real)
_TITULO_CHALLENGE = ('challenge validation', 'access denied', 'pardon our interruption')


class PropiedadesComScraper(BaseScraper):
    """Scraper especializado para fichas de propiedad de Propiedades.com."""

    def __init__(self, output_dir: str = "data", headless: bool = True,
                 descargar_imagenes: bool = True):
        super().__init__(output_dir, headless, descargar_imagenes)
        self.site_name = "propiedades_com"
        self.normalizer = DataNormalizer()

    def get_selectors(self) -> Dict[str, Any]:
        """Selectores de respaldo (la extracción fuerte va por JSON-LD)."""
        return {
            'titulo': ['h1'],
            'precio': [
                '[class*="price"]',
                'text=/\\$[\\d,]+\\s*(MXN|USD)/',
            ],
            'ubicacion': [
                '[class*="location"]',
                '[class*="address"]',
            ],
            'descripcion': [
                '.description-text',
                '[class*="description"]',
            ],
        }

    async def _contenido_listo(self, page: Page) -> bool:
        """True si la página ya muestra contenido real (no el reto de Akamai)."""
        titulo = (await page.title() or '').lower()
        if any(k in titulo for k in _TITULO_CHALLENGE):
            return False
        return len(await page.content()) > 8000

    async def wait_for_page_load(self, page: Page):
        """Resuelve el reto de Akamai con paciencia.

        Akamai sirve primero un "Challenge Validation" cuyo JS hace el sensor y
        se auto-recarga. La clave es ESPERAR a que se resuelva solo; recargar muy
        rápido/muchas veces escala el reto a un "Access Denied" duro. Por eso
        esperamos en tramos y recargamos como mucho una vez.
        """
        # 1) Dar tiempo a que el sensor JS de Akamai se resuelva y auto-recargue
        for _ in range(6):
            if await self._contenido_listo(page):
                await page.wait_for_timeout(1000)
                return
            await page.wait_for_timeout(3000)

        # 2) Último recurso: una sola recarga suave
        try:
            await page.reload(wait_until='networkidle')
        except Exception:
            pass
        await page.wait_for_timeout(4000)

    async def extract_custom_data(self, page: Page, data: Dict) -> Dict:
        """Completa los datos usando el JSON-LD de la ficha + la descripción rica."""
        data['empresa'] = 'Propiedades.com'

        # 1) Datos estructurados JSON-LD (Apartment/House + Offer)
        nodos = await self._extraer_json_ld(page)
        self._aplicar_json_ld(nodos, data)

        # 2) Descripción rica (mejor que la del JSON-LD para el LLM)
        descripcion_rica = await self.extraer_texto(page, ['.description-text'])
        if descripcion_rica and len(descripcion_rica) > len(data.get('descripcion') or ''):
            data['descripcion'] = descripcion_rica.strip()

        # 3) Tipo de propiedad
        if not data.get('tipo_propiedad'):
            data['tipo_propiedad'] = self._inferir_tipo(data)

        # 4) Características (superficie, amenidades)
        data['caracteristicas'] = self._extraer_caracteristicas(data)

        # 5) Imágenes (CDN de propiedades.com); descarga omitida si descargar_imagenes=False
        data['imagenes'] = await self._extraer_imagenes(page, data['url'])
        data['imagenes_descargadas'] = []

        # 6) Normalizar precio + ID de propiedad (id numérico final de la URL)
        if data.get('precio'):
            data['precio_normalizado'] = self.normalizer.normalizar_precio(data['precio'])
        data['property_id'] = self._id_de_url(data['url'])

        return data

    async def _extraer_json_ld(self, page: Page) -> List[Dict[str, Any]]:
        """Devuelve todos los nodos JSON-LD de la ficha como lista de dicts."""
        try:
            bloques = await page.eval_on_selector_all(
                "script[type='application/ld+json']",
                "els => els.map(e => e.textContent)"
            )
        except Exception:
            return []

        nodos: List[Dict[str, Any]] = []
        for bloque in bloques:
            try:
                parsed = json.loads(bloque)
            except Exception:
                continue
            nodos.extend(parsed if isinstance(parsed, list) else [parsed])
        return [n for n in nodos if isinstance(n, dict)]

    def _aplicar_json_ld(self, nodos: List[Dict[str, Any]], data: Dict) -> None:
        """Vuelca los campos del JSON-LD (Apartment/House + Offer) al dict de salida."""
        inmueble = next(
            (n for n in nodos if n.get('@type') in
             ('Apartment', 'House', 'SingleFamilyResidence', 'Residence', 'Product')
             and (n.get('address') or n.get('description') or n.get('name'))),
            None
        )
        oferta = next((n for n in nodos if n.get('@type') == 'Offer' and n.get('price') is not None), None)

        if inmueble:
            # Ubicación: el address de propiedades.com es una cadena completa
            addr = inmueble.get('address')
            if isinstance(addr, str) and addr.strip():
                data['ubicacion'] = addr.strip()
            elif isinstance(addr, dict):
                partes = [addr.get('addressLocality'), addr.get('addressRegion')]
                ubic = ', '.join(p for p in partes if p)
                if ubic:
                    data['ubicacion'] = ubic
            if inmueble.get('description') and not data.get('descripcion'):
                data['descripcion'] = inmueble['description'].strip()

        if oferta:
            moneda = oferta.get('priceCurrency') or 'MXN'
            try:
                precio_num = int(float(oferta['price']))
                data['precio'] = f"${precio_num:,} {moneda}"
            except (ValueError, TypeError):
                data['precio'] = f"{oferta['price']} {moneda}"
            data['moneda'] = moneda
            data['estado'] = 'En venta'

    def _inferir_tipo(self, data: Dict) -> str:
        """Infiere el tipo desde el título/URL."""
        texto = f"{data.get('titulo','')} {data.get('url','')}".lower()
        mapa = {
            'terreno': 'terreno', 'lote': 'terreno',
            'casa': 'casa', 'departamento': 'departamento', 'depto': 'departamento',
            'local': 'local', 'oficina': 'oficina', 'bodega': 'bodega',
            'edificio': 'edificio', 'rancho': 'rancho',
        }
        for clave, valor in mapa.items():
            if clave in texto:
                return valor
        return None

    def _extraer_caracteristicas(self, data: Dict) -> Dict[str, Any]:
        """Detecta superficie en m² y amenidades comunes en la descripción."""
        caracteristicas: Dict[str, Any] = {}
        descripcion = data.get('descripcion') or ''
        titulo = data.get('titulo') or ''
        texto = f"{titulo} {descripcion}"

        m = re.search(r'([\d.,]+)\s*m[²2]', texto)
        if m:
            try:
                caracteristicas['superficie_m2'] = float(m.group(1).replace(',', ''))
            except ValueError:
                pass

        patrones = {
            'alberca': r'alberca|piscina',
            'seguridad': r'seguridad 24/7|acceso controlado|vigilancia|caseta',
            'areas_verdes': r'áreas verdes|areas verdes|jardín|jardin',
            'amenidades': r'amenidades',
            'cochera': r'cochera|estacionamiento',
            'esquina': r'en esquina|esquinero',
        }
        for key, patron in patrones.items():
            if re.search(patron, texto, re.IGNORECASE):
                caracteristicas[key] = True

        rec = re.search(r'(\d+)\s*recámaras?', texto, re.IGNORECASE)
        if rec:
            caracteristicas['recamaras'] = int(rec.group(1))
        ban = re.search(r'(\d+)\s*baños?', texto, re.IGNORECASE)
        if ban:
            caracteristicas['baños'] = int(ban.group(1))

        return caracteristicas

    async def _extraer_imagenes(self, page: Page, url: str) -> List[str]:
        """Extrae las URLs de las fotos de la propiedad (CDN cdn.propiedades.com/files)."""
        try:
            srcs = await page.eval_on_selector_all(
                "img",
                "els => els.map(e => e.getAttribute('src') || e.getAttribute('data-src')).filter(Boolean)"
            )
        except Exception:
            return []

        imagenes: List[str] = []
        for src in srcs:
            img_url = urljoin(url, src)
            # Solo fotos de propiedad del CDN; descartar logos/flags/static
            if 'cdn.propiedades.com/files' not in img_url:
                continue
            limpia = img_url.split('?')[0]
            if limpia not in imagenes:
                imagenes.append(limpia)
        return imagenes

    @staticmethod
    def _id_de_url(url: str) -> str:
        """`.../...-sonterra-residencial-ii-sinaloa-30827156` -> `30827156`."""
        m = re.search(r'-(\d{6,})(?:[/?#]|$)', url or '')
        if m:
            return m.group(1)
        # Fallback: slug completo
        m2 = re.search(r'/inmuebles/([^/?#]+)', url or '')
        return m2.group(1) if m2 else (url or '')


async def main():
    """Prueba rápida del scraper sobre una ficha real."""
    url = ("https://propiedades.com/inmuebles/terreno-habitacional-en-venta-av-paseo-del-pacifico-"
           "km-13-82000-mazatlan-sin-sn-sonterra-residencial-ii-sinaloa-30827156")
    scraper = PropiedadesComScraper(output_dir="data", descargar_imagenes=False)
    resultado = await scraper.extraer_informacion(url)
    print("\n✅ Prueba completada!")
    print(json.dumps(resultado, indent=2, ensure_ascii=False)[:1600])


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
