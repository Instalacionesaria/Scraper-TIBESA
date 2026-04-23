"""
Scraper específico para Lamudi - Mazatlán
https://www.lamudi.com.mx/sinaloa/mazatlan/for-sale/
"""

import re
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin
from playwright.async_api import Page

from .base_scraper import BaseScraper
from utils.image_downloader import ImageDownloader
from utils.data_normalizer import DataNormalizer


class LamudiScraper(BaseScraper):
    """
    Scraper especializado para Lamudi - Mazatlán
    Enfocado en datos de mercado: precio, superficie, tipo, recámaras, etc.
    """

    def __init__(self, output_dir: str = "data", headless: bool = True):
        super().__init__(output_dir, headless)
        self.site_name = "lamudi"
        self.image_downloader = ImageDownloader(str(self.images_dir))
        self.normalizer = DataNormalizer()

    def get_selectors(self) -> Dict[str, Any]:
        return {
            'titulo': [
                'h1',
                '.main-title',
            ],
            'ubicacion': [],  # Se extrae en extract_custom_data con JS
            'precio': [],     # Se extrae en extract_custom_data con JS
            'estado': [],     # Se extrae de features
            'descripcion': [
                '.description-text',
            ],
        }

    async def extract_custom_data(self, page: Page, data: Dict) -> Dict:
        data['empresa'] = 'Lamudi'

        # Extraer precio limpio (sin texto basura del botón "Avísame")
        print("💰 Extrayendo precio...")
        precio_limpio = await page.evaluate("""
            () => {
                // Intentar .price primero
                const priceEl = document.querySelector('.price');
                if (priceEl) {
                    // Solo el primer nodo de texto (antes del botón "Avísame")
                    for (const node of priceEl.childNodes) {
                        if (node.nodeType === 3) { // TEXT_NODE
                            const text = node.textContent.trim();
                            if (text && /[\\d$]/.test(text)) return text;
                        }
                    }
                    // Fallback: primera línea
                    const firstLine = priceEl.textContent.split('\\n')[0].trim();
                    if (/[\\d$]/.test(firstLine)) return firstLine;
                }

                // Fallback: buscar cualquier elemento con precio
                const allText = document.body.textContent;
                const match = allText.match(/(USD|MXN|\\$)\\s*[\\d,]+(?:\\.\\d{2})?/);
                if (match) return match[0];

                return null;
            }
        """)
        if precio_limpio:
            data['precio'] = precio_limpio
            if 'USD' in precio_limpio:
                data['moneda'] = 'USD'
            elif 'MXN' in precio_limpio or '$' in precio_limpio:
                data['moneda'] = 'MXN'
            print(f"   Precio: {precio_limpio}")

        # Extraer ubicación limpia
        print("📍 Extrayendo ubicación...")
        ubicacion = await page.evaluate("""
            () => {
                // Buscar en el breadcrumb (más confiable)
                const breadcrumbs = document.querySelectorAll('.breadcrumb-custom-item, .breadcrumb-custom-item-last');
                if (breadcrumbs.length >= 3) {
                    const parts = [];
                    // Saltar "Venta" (primer breadcrumb), tomar estado, ciudad, colonia
                    for (let i = 1; i < breadcrumbs.length; i++) {
                        const text = breadcrumbs[i].textContent.trim().replace(/[>›]/g, '').trim();
                        if (text) parts.push(text);
                    }
                    if (parts.length > 0) return parts.join(', ');
                }

                // Fallback: buscar en la sección de ubicación
                const locEl = document.querySelector('.location-container span, [class*="location"] span');
                if (locEl) return locEl.textContent.trim();

                return null;
            }
        """)
        if ubicacion:
            data['ubicacion'] = ubicacion
            print(f"   Ubicación: {ubicacion}")

        # Extraer descripción limpia
        if not data.get('descripcion'):
            print("📝 Extrayendo descripción...")
            descripcion = await page.evaluate("""
                () => {
                    const descEl = document.querySelector('.description-text');
                    if (descEl) return descEl.textContent.trim();
                    // Fallback
                    const descContainer = document.querySelector('[class*="description"]');
                    if (descContainer) {
                        const p = descContainer.querySelector('p');
                        if (p) return p.textContent.trim();
                        return descContainer.textContent.trim().substring(0, 2000);
                    }
                    return null;
                }
            """)
            if descripcion:
                # Limpiar el prefijo "Descripción" si viene incluido
                descripcion = re.sub(r'^Descripción\s*', '', descripcion).strip()
                data['descripcion'] = descripcion
                preview = descripcion[:100] + '...' if len(descripcion) > 100 else descripcion
                print(f"   Descripción: {preview}")

        # Extraer datos de la ficha técnica (recámaras, baños, superficie)
        print("📐 Extrayendo ficha técnica...")
        data['ficha_tecnica'] = await self._extraer_ficha_tecnica(page)

        # Extraer tipo de propiedad directamente de place-details
        print("🏷️  Extrayendo tipo de propiedad...")
        tipo_propiedad = await page.evaluate("""
            () => {
                // Buscar "Tipo de vivienda: X" en place-details
                const details = document.querySelector('.place-details');
                if (details) {
                    const text = details.textContent;
                    const match = text.match(/Tipo de vivienda:\\s*([\\wáéíóúñÁÉÍÓÚÑ\\s]+?)(?:\\n|Tipo de op)/i);
                    if (match) return match[1].trim();
                }
                // Fallback: buscar en features
                const features = document.querySelectorAll('.place-features__values');
                for (const f of features) {
                    const t = f.textContent.trim().toLowerCase();
                    if (t.includes('casa') || t.includes('departamento') || t.includes('terreno') ||
                        t.includes('local') || t.includes('bodega') || t.includes('oficina') ||
                        t.includes('edificio') || t.includes('rancho')) {
                        return f.textContent.trim();
                    }
                }
                return null;
            }
        """)
        if tipo_propiedad:
            data['tipo_propiedad'] = tipo_propiedad.lower()
            print(f"   Tipo: {tipo_propiedad}")

        # Mapear ficha técnica a campos estándar
        ficha = data['ficha_tecnica']
        if ficha.get('recamaras'):
            data.setdefault('caracteristicas', {})['recamaras'] = ficha['recamaras']
        if ficha.get('banos'):
            data.setdefault('caracteristicas', {})['banos'] = ficha['banos']
        if ficha.get('superficie_m2'):
            data['terreno'] = {
                'superficie': f"{ficha['superficie_m2']} m²",
                'superficie_m2': ficha['superficie_m2'],
            }
        if ficha.get('superficie_construida_m2'):
            data['terreno']['superficie_construida'] = f"{ficha['superficie_construida_m2']} m²"
            data['terreno']['superficie_construida_m2'] = ficha['superficie_construida_m2']

        # Extraer features adicionales (tipo vivienda, año, estado, etc.)
        print("🏠 Extrayendo características del inmueble...")
        features = await self._extraer_features(page)
        if not data.get('tipo_propiedad') and features.get('tipo_vivienda'):
            data['tipo_propiedad'] = features['tipo_vivienda'].lower()
        data['tipo_operacion'] = features.get('tipo_operacion', 'Venta')
        if features.get('ano_construccion'):
            data.setdefault('caracteristicas', {})['ano_construccion'] = features['ano_construccion']
        if features.get('estado_propiedad'):
            data.setdefault('caracteristicas', {})['estado_propiedad'] = features['estado_propiedad']
        if features.get('estacionamientos'):
            data.setdefault('caracteristicas', {})['estacionamientos'] = features['estacionamientos']
        if features.get('pisos'):
            data.setdefault('caracteristicas', {})['pisos'] = features['pisos']

        # Extraer amenidades
        print("✨ Extrayendo amenidades...")
        amenidades = await self._extraer_amenidades(page)
        if amenidades:
            data.setdefault('caracteristicas', {})['amenidades'] = amenidades

        # Extraer agente / anunciante
        print("👤 Extrayendo información del anunciante...")
        data['agente'] = await self._extraer_agente(page)

        # Normalizar precio
        if data.get('precio'):
            data['precio_normalizado'] = self.normalizer.normalizar_precio(data['precio'])

        # Extraer ID de propiedad desde URL de Lamudi
        property_id = self._extraer_id_lamudi(data['url'])
        if property_id:
            data['property_id'] = property_id

        # Descargar solo 1 imagen representativa
        print("🖼️  Extrayendo imagen principal...")
        data['imagenes'], data['imagenes_descargadas'] = await self._extraer_imagen_principal(page, data['url'])

        return data

    async def _extraer_ficha_tecnica(self, page: Page) -> Dict[str, Any]:
        """Extrae recámaras, baños y superficie de los iconos de detalle"""
        ficha = {}

        try:
            # Recámaras: .details-item con icono de cama
            recamaras_elem = await page.query_selector('.details-item__icon-bed')
            if recamaras_elem:
                parent = await recamaras_elem.evaluate_handle('el => el.closest(".details-item")')
                value_elem = await parent.query_selector('.details-item-value')
                if value_elem:
                    texto = (await value_elem.text_content()).strip()
                    nums = re.findall(r'\d+', texto)
                    if nums:
                        ficha['recamaras'] = int(nums[0])
                        print(f"   Recámaras: {ficha['recamaras']}")

            # Baños: .details-item con icono de baño
            banos_elem = await page.query_selector('.details-item__icon-bath')
            if banos_elem:
                parent = await banos_elem.evaluate_handle('el => el.closest(".details-item")')
                value_elem = await parent.query_selector('.details-item-value')
                if value_elem:
                    texto = (await value_elem.text_content()).strip()
                    nums = re.findall(r'[\d.]+', texto)
                    if nums:
                        ficha['banos'] = float(nums[0])
                        print(f"   Baños: {ficha['banos']}")

            # Superficie: .details-item con icono de area
            area_elem = await page.query_selector('.details-item__icon-area')
            if area_elem:
                parent = await area_elem.evaluate_handle('el => el.closest(".details-item")')
                value_elem = await parent.query_selector('.details-item-value')
                if value_elem:
                    texto = (await value_elem.text_content()).strip()
                    nums = re.findall(r'[\d,.]+', texto)
                    if nums:
                        valor = float(nums[0].replace(',', ''))
                        ficha['superficie_m2'] = valor
                        print(f"   Superficie: {valor} m²")

            # Superficie construida (puede estar en .floor-area o en features)
            floor_area = await page.query_selector('.floor-area .details-item-value')
            if floor_area:
                texto = (await floor_area.text_content()).strip()
                nums = re.findall(r'[\d,.]+', texto)
                if nums:
                    ficha['superficie_construida_m2'] = float(nums[0].replace(',', ''))
                    print(f"   Superficie construida: {ficha['superficie_construida_m2']} m²")

            # Fallback: buscar con evaluación JS todos los details-item
            if not ficha:
                ficha = await self._extraer_ficha_js(page)

        except Exception as e:
            print(f"   ⚠ Error extrayendo ficha técnica: {e}")

        return ficha

    async def _extraer_ficha_js(self, page: Page) -> Dict[str, Any]:
        """Fallback: extrae ficha técnica via JavaScript"""
        try:
            return await page.evaluate("""
                () => {
                    const ficha = {};
                    const items = document.querySelectorAll('.details-item');
                    for (const item of items) {
                        const icon = item.querySelector('[class*="icon"]');
                        const value = item.querySelector('.details-item-value');
                        if (!icon || !value) continue;

                        const iconClass = icon.className || '';
                        const texto = value.textContent.trim();
                        const nums = texto.match(/[\\d,.]+/);
                        if (!nums) continue;

                        const val = parseFloat(nums[0].replace(',', ''));
                        if (iconClass.includes('bed')) ficha.recamaras = val;
                        else if (iconClass.includes('bath')) ficha.banos = val;
                        else if (iconClass.includes('area')) ficha.superficie_m2 = val;
                    }
                    return ficha;
                }
            """)
        except:
            return {}

    async def _extraer_features(self, page: Page) -> Dict[str, Any]:
        """Extrae tipo de vivienda, año de construcción, estado, etc."""
        features = {}

        try:
            result = await page.evaluate("""
                () => {
                    const features = {};
                    const rows = document.querySelectorAll('.place-features__values');
                    for (const row of rows) {
                        const text = row.textContent.trim();

                        // El texto tiene formato "Label: Valor" o similar
                        const cells = row.querySelectorAll('div, span, li');
                        for (const cell of cells) {
                            const t = cell.textContent.trim().toLowerCase();
                            if (!t) continue;

                            // Mapear valores conocidos
                            if (t.includes('casa') || t.includes('departamento') ||
                                t.includes('terreno') || t.includes('local') ||
                                t.includes('bodega') || t.includes('oficina') ||
                                t.includes('rancho') || t.includes('edificio')) {
                                features.tipo_vivienda = cell.textContent.trim();
                            }
                        }
                    }

                    // Buscar en la sección de place-details
                    const allText = document.querySelector('.place-details')?.textContent || '';

                    // Tipo de vivienda
                    const tipoMatch = allText.match(/Tipo de vivienda:\\s*([\\w\\s]+?)(?:\\n|$)/i);
                    if (tipoMatch) features.tipo_vivienda = tipoMatch[1].trim();

                    // Tipo de operación
                    const opMatch = allText.match(/Tipo de operación:\\s*([\\w\\s]+?)(?:\\n|$)/i);
                    if (opMatch) features.tipo_operacion = opMatch[1].trim();

                    // Año de construcción
                    const anoMatch = allText.match(/Año de construcción:\\s*(\\d{4})/i) ||
                                    allText.match(/construcción:\\s*(\\d{4})/i);
                    if (anoMatch) features.ano_construccion = parseInt(anoMatch[1]);

                    // Estado
                    const estadoMatch = allText.match(/Estado:\\s*([\\w\\s]+?)(?:\\n|$)/i);
                    if (estadoMatch) features.estado_propiedad = estadoMatch[1].trim();

                    // Estacionamientos
                    const estMatch = allText.match(/Estacionamientos?:\\s*(\\d+)/i);
                    if (estMatch) features.estacionamientos = parseInt(estMatch[1]);

                    // Pisos / Plantas
                    const pisosMatch = allText.match(/Pisos?:\\s*(\\d+)/i) ||
                                      allText.match(/Plantas?:\\s*(\\d+)/i);
                    if (pisosMatch) features.pisos = parseInt(pisosMatch[1]);

                    // Superficie de terreno (si no se captó antes)
                    const supTerreno = allText.match(/Superficie (?:útil|del terreno|total):\\s*([\\.\\d,]+)\\s*m/i);
                    if (supTerreno) features.superficie_terreno_m2 = parseFloat(supTerreno[1].replace(',', ''));

                    return features;
                }
            """)

            if result:
                features = result
                for k, v in features.items():
                    print(f"   {k}: {v}")

        except Exception as e:
            print(f"   ⚠ Error extrayendo features: {e}")

        return features

    async def _extraer_amenidades(self, page: Page) -> List[str]:
        """Extrae la lista de amenidades/facilidades"""
        amenidades = []

        try:
            result = await page.evaluate("""
                () => {
                    const amenidades = [];
                    // Buscar en sección de facilities
                    const facilityElements = document.querySelectorAll(
                        '.facilities li, .facilities span, ' +
                        '[class*="amenity"] li, [class*="amenity"] span, ' +
                        '[class*="facility"] li, [class*="facility"] span'
                    );
                    for (const el of facilityElements) {
                        const text = el.textContent.trim();
                        if (text && text.length > 1 && text.length < 60 &&
                            !text.includes('Ver más') && !text.includes('Ver menos')) {
                            amenidades.push(text);
                        }
                    }

                    // Fallback: buscar en listing-tags si hay
                    if (amenidades.length === 0) {
                        const tags = document.querySelectorAll('.listing-tag');
                        for (const tag of tags) {
                            const text = tag.textContent.trim();
                            if (text && text.length > 1) amenidades.push(text);
                        }
                    }

                    return [...new Set(amenidades)];
                }
            """)

            if result:
                amenidades = result
                if amenidades:
                    print(f"   Amenidades: {', '.join(amenidades[:8])}{'...' if len(amenidades) > 8 else ''}")

        except Exception as e:
            print(f"   ⚠ Error extrayendo amenidades: {e}")

        return amenidades

    async def _extraer_agente(self, page: Page) -> Dict[str, str]:
        """Extrae información del anunciante/agente"""
        agente = {}

        try:
            # Nombre del agente
            nombre_elem = await page.query_selector(
                '.agent-name, [class*="agent"] .name, '
                '[data-qa="agent-name"], .contact-agent-name'
            )
            if nombre_elem:
                agente['nombre'] = (await nombre_elem.text_content()).strip()

            # Fallback: buscar en el sidebar de contacto
            if not agente.get('nombre'):
                result = await page.evaluate("""
                    () => {
                        // Buscar nombre del agente en el sidebar
                        const contactSection = document.querySelector(
                            '[class*="contact"], [class*="agent"], [class*="advertiser"]'
                        );
                        if (!contactSection) return null;

                        const text = contactSection.textContent;
                        // Buscar líneas que parezcan nombres (mayúsculas, 2+ palabras)
                        const lines = text.split('\\n').map(l => l.trim()).filter(l => l.length > 3);
                        for (const line of lines) {
                            if (/^[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+ [A-ZÁÉÍÓÚÑ]/.test(line) && line.length < 60) {
                                return line;
                            }
                        }
                        return null;
                    }
                """)
                if result:
                    agente['nombre'] = result

            # Teléfono (puede estar oculto detrás de un botón)
            tel_elem = await page.query_selector('a[href*="tel:"]')
            if tel_elem:
                href = await tel_elem.get_attribute('href')
                if href:
                    telefono = href.replace('tel:', '').strip()
                    telefono_norm = self.normalizer.normalizar_telefono(telefono)
                    if telefono_norm:
                        agente['telefono'] = telefono_norm

            if agente:
                print(f"   Agente: {agente.get('nombre', 'N/A')}")

        except Exception as e:
            print(f"   ⚠ Error extrayendo agente: {e}")

        return agente

    async def _extraer_imagen_principal(self, page: Page, url: str) -> tuple:
        """Extrae y descarga solo la imagen principal de la propiedad"""
        urls_imagenes = []
        imagenes_descargadas = []

        try:
            # Buscar la primera imagen de la galería
            img_url = await page.evaluate("""
                () => {
                    // Buscar en galería
                    const galleryImg = document.querySelector(
                        '.gallery__slide img, [class*="gallery"] img, ' +
                        '[class*="carousel"] img, [class*="slider"] img, ' +
                        '.photos img'
                    );
                    if (galleryImg) {
                        return galleryImg.src || galleryImg.dataset.src || null;
                    }

                    // Fallback: primera imagen grande de la página
                    const imgs = document.querySelectorAll('img[src*="lamudi"], img[src*="property"], img[src*="image"]');
                    for (const img of imgs) {
                        const src = img.src || img.dataset.src;
                        if (src && !src.includes('logo') && !src.includes('icon') && !src.includes('avatar')) {
                            return src;
                        }
                    }
                    return null;
                }
            """)

            if img_url:
                urls_imagenes = [img_url]
                property_id = self._extraer_id_lamudi(url) or 'unknown'
                carpeta = f"lamudi_{property_id}"

                imagenes_descargadas = await self.image_downloader.descargar_multiples(
                    [img_url],
                    prefijo="lamudi",
                    carpeta_propiedad=carpeta
                )
                print(f"   ✅ Imagen principal descargada")
            else:
                print(f"   ⚠ No se encontró imagen principal")

        except Exception as e:
            print(f"   ⚠ Error extrayendo imagen: {e}")

        return urls_imagenes, imagenes_descargadas

    @staticmethod
    def _extraer_id_lamudi(url: str) -> Optional[str]:
        """Extrae el ID único de una URL de Lamudi (/detalle/xxxxx)"""
        match = re.search(r'/detalle/(.+?)(?:\?|$)', url)
        if match:
            return match.group(1)
        return None

    async def wait_for_page_load(self, page: Page):
        """Espera específica para Lamudi - contenido dinámico"""
        try:
            await page.wait_for_selector('h1', timeout=15000)
        except:
            pass
        await page.wait_for_timeout(2000)


async def main():
    """Función de prueba con una propiedad de ejemplo"""
    url = "https://www.lamudi.com.mx/detalle/41032-73-82a574bc77a7-ae14-19b7082-9604-778c"

    scraper = LamudiScraper(output_dir="data")
    resultado = await scraper.extraer_informacion(url)

    print("\n📊 DATOS EXTRAÍDOS:")
    for key, value in resultado.items():
        if key not in ('imagenes', 'imagenes_descargadas'):
            print(f"   {key}: {value}")

    print("\n✅ Prueba completada!")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
