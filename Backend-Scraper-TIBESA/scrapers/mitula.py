"""
Scraper específico para Mitula - Mazatlán
https://casas.mitula.mx/casas/casas-mazatlan

Mitula es un agregador: toda la información está en las cards del listado,
no hay páginas de detalle individual. El scraping se hace directamente
del listado paginado.
"""

import re
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright, Page

from utils.image_downloader import ImageDownloader
from utils.data_normalizer import DataNormalizer


class MitulaScraper:
    """
    Scraper especializado para Mitula - Mazatlán.
    A diferencia de otros scrapers, este extrae datos directamente
    de las cards del listado (no navega a páginas de detalle).
    """

    LISTADO_URL = "https://casas.mitula.mx/casas/casas-mazatlan"

    def __init__(self, output_dir: str = "data", headless: bool = True):
        self.output_dir = Path(output_dir)
        self.json_dir = self.output_dir / "json"
        self.images_dir = self.output_dir / "imagenes"
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.site_name = "mitula"
        self.image_downloader = ImageDownloader(str(self.images_dir))
        self.normalizer = DataNormalizer()

    async def extraer_todas_las_propiedades(self, callback=None, max_pages: int = 0):
        """
        Scrapea todas las páginas del listado de Mitula.

        Args:
            callback: async function(event, data) para reportar progreso
            max_pages: Límite de páginas (0 = sin límite)

        Returns:
            list: Lista de propiedades extraídas
        """
        todas = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=['--disable-blink-features=AutomationControlled']
            )
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                           'Chrome/120.0.0.0 Safari/537.36',
                locale='es-MX',
                timezone_id='America/Mexico_City',
            )
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            """)

            page = await context.new_page()
            num_pagina = 1

            while True:
                page_url = self.LISTADO_URL if num_pagina == 1 else f"{self.LISTADO_URL}?page={num_pagina}"
                print(f"\n📄 Mitula - Página {num_pagina}: {page_url}")

                try:
                    await page.goto(page_url, wait_until='networkidle', timeout=60000)
                    await page.wait_for_timeout(3000)

                    # Scroll para cargar lazy images
                    await page.evaluate("""async () => {
                        await new Promise(r => {
                            let h = 0; const d = 300;
                            const t = setInterval(() => {
                                window.scrollBy(0, d); h += d;
                                if (h >= document.body.scrollHeight) { clearInterval(t); r(); }
                            }, 80);
                        });
                    }""")
                    await page.wait_for_timeout(1500)

                except Exception as e:
                    print(f"   ❌ Error cargando página {num_pagina}: {e}")
                    break

                # Extraer cards de esta página
                cards = await self._extraer_cards(page)

                if not cards:
                    print("   → Sin propiedades, fin de la paginación")
                    break

                print(f"   → {len(cards)} propiedades extraídas")

                # Procesar cada card
                for card in cards:
                    card['site'] = self.site_name
                    card['empresa'] = 'Mitula'
                    card['fecha_scraping'] = datetime.now().isoformat()

                    # Descargar 1 imagen
                    if card.get('imagen_url'):
                        prop_id = card.get('property_id', len(todas) + 1)
                        carpeta = f"mitula_{prop_id}"
                        try:
                            descargadas = await self.image_downloader.descargar_multiples(
                                [card['imagen_url']],
                                prefijo="mitula",
                                carpeta_propiedad=carpeta,
                            )
                            card['imagenes_descargadas'] = descargadas
                        except Exception:
                            card['imagenes_descargadas'] = []

                    # Guardar JSON individual
                    prop_id = card.get('property_id', len(todas) + 1)
                    json_path = self.json_dir / f"mitula_{prop_id}.json"
                    import json
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(card, f, indent=2, ensure_ascii=False)

                    todas.append(card)

                    # Callback para progreso en tiempo real
                    if callback:
                        await callback('property', card)

                # Verificar si hay más páginas
                has_next = await page.query_selector(
                    f'.pagination__page a[href*="page={num_pagina + 1}"]'
                )
                if not has_next or (max_pages > 0 and num_pagina >= max_pages):
                    print("   → Fin de la paginación")
                    break

                num_pagina += 1
                await page.wait_for_timeout(2000)

            await browser.close()

        print(f"\n✅ Total propiedades scrapeadas: {len(todas)}")
        return todas

    async def _extraer_cards(self, page: Page) -> List[Dict[str, Any]]:
        """Extrae datos de todas las cards de una página del listado"""
        raw_cards = await page.evaluate("""
            () => {
                const cards = document.querySelectorAll('.listing-card');
                const results = [];

                for (const card of cards) {
                    const data = {};

                    // Precio
                    const price = card.querySelector('.price__actual');
                    data.precio_texto = price ? price.textContent.trim() : null;

                    // Ubicación
                    const location = card.querySelector('.listing-card__location__geo');
                    data.ubicacion = location ? location.textContent.trim() : null;

                    // Recámaras
                    const bedIcon = card.querySelector('.listing-card__icon__bedrooms');
                    if (bedIcon) {
                        const parent = bedIcon.closest('.listing-card__properties__property');
                        data.recamaras_texto = parent ? parent.textContent.trim() : null;
                    }

                    // Baños
                    const bathIcon = card.querySelector('.listing-card__icon__bathrooms');
                    if (bathIcon) {
                        const parent = bathIcon.closest('.listing-card__properties__property');
                        data.banos_texto = parent ? parent.textContent.trim() : null;
                    }

                    // Superficie
                    const areaIcon = card.querySelector('.listing-card__icon__area');
                    if (areaIcon) {
                        const parent = areaIcon.closest('.listing-card__properties__property');
                        data.superficie_texto = parent ? parent.textContent.trim() : null;
                    }

                    // Tipo de propiedad (tag)
                    const typeTag = card.querySelector('.tag--listing--property-type');
                    data.tipo_propiedad = typeTag ? typeTag.textContent.trim() : null;

                    // Amenidades
                    const facilities = card.querySelectorAll('.listing-card__facilities__facility');
                    data.amenidades = [];
                    for (const f of facilities) {
                        const text = f.textContent.trim();
                        if (text) data.amenidades.push(text);
                    }

                    // Descripción
                    const desc = card.querySelector('.listing-card__description__text');
                    data.descripcion = desc ? desc.textContent.trim() : null;

                    // Imagen principal
                    const img = card.querySelector('.swiper-slide-active img, .swiper-slide img');
                    data.imagen_url = img ? (img.src || img.dataset?.src || null) : null;

                    // Agencia / publicado por
                    const agency = card.querySelector(
                        '.listing-card__information__bottom__published-date-and-agency'
                    );
                    data.agencia_texto = agency ? agency.textContent.trim() : null;

                    // Tags especiales
                    const specialTags = card.querySelectorAll('.tag--listing--special-characteristic');
                    data.tags = [];
                    for (const t of specialTags) {
                        data.tags.push(t.textContent.trim());
                    }

                    results.push(data);
                }
                return results;
            }
        """)

        # Post-procesar cada card
        propiedades = []
        for i, raw in enumerate(raw_cards):
            prop = self._procesar_card(raw, i)
            propiedades.append(prop)

        return propiedades

    def _procesar_card(self, raw: Dict, index: int) -> Dict[str, Any]:
        """Procesa y normaliza los datos crudos de una card"""
        prop = {
            'url': None,  # Mitula no tiene páginas individuales
            'titulo': self._generar_titulo(raw),
            'ubicacion': raw.get('ubicacion'),
            'tipo_propiedad': raw.get('tipo_propiedad', '').lower() if raw.get('tipo_propiedad') else None,
            'tipo_operacion': 'Venta',
            'descripcion': raw.get('descripcion'),
            'imagen_url': raw.get('imagen_url'),
            'imagenes': [raw['imagen_url']] if raw.get('imagen_url') else [],
            'imagenes_descargadas': [],
            'caracteristicas': {
                'amenidades': raw.get('amenidades', []),
            },
            'terreno': {},
            'agente': {},
            'tags': raw.get('tags', []),
        }

        # Precio
        precio_texto = raw.get('precio_texto', '')
        if precio_texto:
            prop['precio'] = precio_texto
            norm = self.normalizer.normalizar_precio(precio_texto)
            prop['precio_normalizado'] = norm
            prop['moneda'] = norm.get('moneda') or ('MXN' if 'MXN' in precio_texto else None)

        # Recámaras
        if raw.get('recamaras_texto'):
            nums = re.findall(r'[\d]+', raw['recamaras_texto'])
            if nums:
                prop['caracteristicas']['recamaras'] = int(nums[0])

        # Baños
        if raw.get('banos_texto'):
            nums = re.findall(r'[\d.]+', raw['banos_texto'])
            if nums:
                prop['caracteristicas']['banos'] = float(nums[0])

        # Superficie
        if raw.get('superficie_texto'):
            nums = re.findall(r'[\d,.]+', raw['superficie_texto'])
            if nums:
                val = float(nums[0].replace(',', ''))
                prop['terreno'] = {
                    'superficie': f"{val} m²",
                    'superficie_m2': val,
                }

        # Agencia
        if raw.get('agencia_texto'):
            # Formato: "Hace X semanas, Y días en - NOMBRE AGENCIA"
            match = re.search(r'(?:en\s*-\s*|en\s+)(.+)$', raw['agencia_texto'])
            if match:
                prop['agente'] = {'nombre': match.group(1).strip()}

        # Property ID (hash del título + ubicación para deduplicación)
        id_base = f"{prop.get('titulo', '')}{prop.get('ubicacion', '')}{prop.get('precio', '')}"
        prop['property_id'] = str(abs(hash(id_base)))[:10]

        return prop

    @staticmethod
    def _generar_titulo(raw: Dict) -> str:
        """Genera un título descriptivo a partir de los datos de la card"""
        parts = []
        tipo = raw.get('tipo_propiedad', '')
        if tipo:
            parts.append(tipo)
        else:
            parts.append('Propiedad')

        parts.append('en venta')

        ubicacion = raw.get('ubicacion', '')
        if ubicacion:
            parts.append(f'en {ubicacion}')

        return ' '.join(parts)


# =============================================
# Función standalone para extraer URLs (compatibilidad con main.py)
# =============================================

async def extraer_urls_mitula() -> List[str]:
    """
    Mitula no tiene URLs individuales. Esta función retorna IDs placeholder
    para mantener compatibilidad con el flujo de main.py.
    En realidad el scraping se hace completo en extraer_todas_las_propiedades.
    """
    return []


async def main():
    """Función de prueba - scrapea solo 2 páginas"""
    scraper = MitulaScraper(output_dir="data")
    propiedades = await scraper.extraer_todas_las_propiedades(max_pages=1)

    print(f"\n📊 RESUMEN: {len(propiedades)} propiedades")
    for i, p in enumerate(propiedades[:5]):
        print(f"\n--- Propiedad {i+1} ---")
        print(f"   Título:     {p.get('titulo')}")
        print(f"   Precio:     {p.get('precio')}")
        print(f"   Ubicación:  {p.get('ubicacion')}")
        print(f"   Tipo:       {p.get('tipo_propiedad')}")
        print(f"   Recámaras:  {p.get('caracteristicas', {}).get('recamaras', 'N/A')}")
        print(f"   Baños:      {p.get('caracteristicas', {}).get('banos', 'N/A')}")
        print(f"   Superficie: {p.get('terreno', {}).get('superficie_m2', 'N/A')} m²")
        print(f"   Amenidades: {len(p.get('caracteristicas', {}).get('amenidades', []))}")
        print(f"   Agencia:    {p.get('agente', {}).get('nombre', 'N/A')}")
        print(f"   Imagen:     {'✅' if p.get('imagenes_descargadas') else '❌'}")


if __name__ == "__main__":
    asyncio.run(main())
