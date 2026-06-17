"""
Scraper específico para Pincali (portal nacional agregado)
https://www.pincali.com

Particularidades:
- El sitio está protegido por AWS WAF (action: challenge). Solo un navegador
  real (Playwright) que ejecuta el reto JS obtiene la cookie `aws-waf-token`;
  HTTP plano (requests/aiohttp) recibe 202 con cuerpo vacío. Por eso es un
  scraper de DETALLE (Playwright), igual que Paraíso Dorado / Lamudi.
- Cada ficha trae datos estructurados JSON-LD (@type Product), que es la fuente
  más fiable para precio, superficie, ubicación y tipo. La descripción rica se
  toma de `.listing__description`.
"""

import json
import re
from typing import Dict, Any, List
from urllib.parse import urljoin
from playwright.async_api import Page

from .base_scraper import BaseScraper
from utils.data_normalizer import DataNormalizer


class PincaliScraper(BaseScraper):
    """Scraper especializado para fichas de propiedad de Pincali."""

    def __init__(self, output_dir: str = "data", headless: bool = True,
                 descargar_imagenes: bool = True):
        super().__init__(output_dir, headless, descargar_imagenes)
        self.site_name = "pincali"
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
                '.listing__location',
                '[class*="location"]',
                'text=/.*Mazatlán.*/',
            ],
            'descripcion': [
                '.listing__description',
                '[class*="description"]',
            ],
        }

    async def extract_custom_data(self, page: Page, data: Dict) -> Dict:
        """Completa los datos usando el JSON-LD de la ficha + la descripción rica."""
        data['empresa'] = 'Pincali'

        # 1) Datos estructurados JSON-LD (@type Product / SingleFamilyResidence)
        producto = await self._extraer_json_ld_producto(page)
        if producto:
            self._aplicar_json_ld(producto, data)

        # 2) Descripción rica (mejor que la corta del JSON-LD para el LLM)
        descripcion_rica = await self.extraer_texto(page, ['.listing__description'])
        if descripcion_rica and len(descripcion_rica) > len(data.get('descripcion') or ''):
            data['descripcion'] = descripcion_rica.strip()

        # 3) Tipo de propiedad (si el JSON-LD no lo trajo)
        if not data.get('tipo_propiedad'):
            data['tipo_propiedad'] = self._inferir_tipo(data)

        # 4) Características visibles (amenidades, superficie)
        data['caracteristicas'] = await self._extraer_caracteristicas(page, data)

        # 5) Imágenes (se omite la descarga cuando descargar_imagenes=False)
        imagenes = await self._extraer_imagenes(page, data['url'])
        data['imagenes'] = imagenes
        data['imagenes_descargadas'] = []

        # 6) Normalizar precio e ID de propiedad (slug de la URL)
        if data.get('precio'):
            data['precio_normalizado'] = self.normalizer.normalizar_precio(data['precio'])
        data['property_id'] = self._slug_de_url(data['url'])

        return data

    async def _extraer_json_ld_producto(self, page: Page) -> Dict[str, Any]:
        """Devuelve el nodo JSON-LD cuyo @type incluye 'Product', o {}."""
        try:
            bloques = await page.eval_on_selector_all(
                "script[type='application/ld+json']",
                "els => els.map(e => e.textContent)"
            )
        except Exception:
            return {}

        for bloque in bloques:
            try:
                parsed = json.loads(bloque)
            except Exception:
                continue
            items = parsed if isinstance(parsed, list) else [parsed]
            for it in items:
                if not isinstance(it, dict):
                    continue
                tipo = it.get('@type')
                tipos = tipo if isinstance(tipo, list) else [tipo]
                if 'Product' in tipos or 'SingleFamilyResidence' in tipos:
                    return it
        return {}

    def _aplicar_json_ld(self, prod: Dict[str, Any], data: Dict) -> None:
        """Vuelca los campos del JSON-LD sobre el dict de salida (pisa los frágiles)."""
        if prod.get('name'):
            data['titulo'] = prod['name'].strip()

        # Precio + moneda desde offers
        offers = prod.get('offers')
        oferta = offers[0] if isinstance(offers, list) and offers else (offers if isinstance(offers, dict) else None)
        if oferta and oferta.get('price') is not None:
            moneda = oferta.get('priceCurrency') or 'MXN'
            try:
                precio_num = int(float(oferta['price']))
                data['precio'] = f"${precio_num:,} {moneda}"
            except (ValueError, TypeError):
                data['precio'] = f"{oferta['price']} {moneda}"
            data['moneda'] = moneda

        # Disponibilidad → estado (En venta / vendido)
        disp = (oferta or {}).get('availability', '') if oferta else ''
        if 'InStock' in disp:
            data['estado'] = 'En venta'

        # Ubicación desde address
        addr = prod.get('address') or {}
        if isinstance(addr, dict):
            partes = [addr.get('addressLocality'), addr.get('addressRegion')]
            ubic = ', '.join(p for p in partes if p)
            if ubic:
                data['ubicacion'] = ubic

        # Tipo de propiedad desde category
        if prod.get('category'):
            data['tipo_propiedad'] = self.normalizer_tipo(prod['category'])

        # Superficie desde floorSize (unitCode MTK = m²)
        floor = prod.get('floorSize') or {}
        if isinstance(floor, dict) and floor.get('value') is not None:
            try:
                data['terreno'] = {'superficie_m2': float(floor['value'])}
            except (ValueError, TypeError):
                pass

        # Descripción corta de respaldo
        if prod.get('description') and not data.get('descripcion'):
            data['descripcion'] = prod['description'].strip()

    @staticmethod
    def normalizer_tipo(categoria: str) -> str:
        """Normaliza la categoría de Pincali a la taxonomía interna."""
        c = (categoria or '').lower()
        mapa = {
            'terreno': 'terreno', 'lote': 'terreno',
            'casa': 'casa', 'departamento': 'departamento', 'depto': 'departamento',
            'local': 'local', 'oficina': 'oficina', 'bodega': 'bodega',
            'edificio': 'edificio', 'rancho': 'rancho',
        }
        for clave, valor in mapa.items():
            if clave in c:
                return valor
        return c or None

    def _inferir_tipo(self, data: Dict) -> str:
        """Infiere el tipo desde el título/URL si el JSON-LD no lo trajo."""
        texto = f"{data.get('titulo','')} {data.get('url','')}".lower()
        return self.normalizer_tipo(texto)

    async def _extraer_caracteristicas(self, page: Page, data: Dict) -> Dict[str, Any]:
        """Detecta amenidades comunes en la descripción y la superficie en m²."""
        caracteristicas: Dict[str, Any] = {}
        descripcion = (data.get('descripcion') or '')

        patrones = {
            'alberca': r'alberca|piscina',
            'seguridad': r'seguridad 24/7|seguridad 24 ?hrs|acceso controlado|vigilancia',
            'areas_verdes': r'áreas verdes|areas verdes|jardín|jardin',
            'escriturado': r'escriturado|escrituras',
            'cochera': r'cochera|estacionamiento|estacionarse',
            'cerca_mar': r'cerca(no)? (al|del) mar|frente al mar|a la playa',
        }
        for key, patron in patrones.items():
            if re.search(patron, descripcion, re.IGNORECASE):
                caracteristicas[key] = True

        # Superficie m² (del JSON-LD o del texto)
        terreno = data.get('terreno') or {}
        if terreno.get('superficie_m2'):
            caracteristicas['superficie_m2'] = terreno['superficie_m2']
        else:
            m = re.search(r'([\d.,]+)\s*m[²2]', descripcion)
            if m:
                try:
                    caracteristicas['superficie_m2'] = float(m.group(1).replace(',', ''))
                except ValueError:
                    pass

        # Recámaras / baños (para casas/deptos)
        rec = re.search(r'(\d+)\s*recámaras?', descripcion, re.IGNORECASE)
        if rec:
            caracteristicas['recamaras'] = int(rec.group(1))
        ban = re.search(r'(\d+)\s*baños?', descripcion, re.IGNORECASE)
        if ban:
            caracteristicas['baños'] = int(ban.group(1))

        return caracteristicas

    async def _extraer_imagenes(self, page: Page, url: str) -> List[str]:
        """Extrae las URLs de las fotos de la propiedad (CDN easybroker)."""
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
            # Solo fotos de la propiedad; descartar logos de organización y fotos de perfil de agente
            if 'property_images' not in img_url:
                continue
            # Quitar parámetros de redimensionado para quedarnos con la original
            limpia = img_url.split('?')[0]
            if limpia not in imagenes:
                imagenes.append(limpia)
        return imagenes

    @staticmethod
    def _slug_de_url(url: str) -> str:
        """`https://www.pincali.com/inmueble/lote-17-...` -> `lote-17-...`"""
        m = re.search(r'/inmueble/([^/?#]+)', url or '')
        return m.group(1) if m else (url or '')


async def main():
    """Prueba rápida del scraper sobre una ficha real."""
    url = "https://www.pincali.com/inmueble/lote-17-en-venta-en-maralto-residencial-cercano-al-mar"
    scraper = PincaliScraper(output_dir="data", descargar_imagenes=False)
    resultado = await scraper.extraer_informacion(url)
    print("\n✅ Prueba completada!")
    print(json.dumps(resultado, indent=2, ensure_ascii=False)[:1500])


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
