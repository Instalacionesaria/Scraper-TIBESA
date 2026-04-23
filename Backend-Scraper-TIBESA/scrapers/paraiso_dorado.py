"""
Scraper específico para Paraíso Dorado
https://paraisodorado.com.mx
"""

import re
from typing import Dict, Any, List
from urllib.parse import urljoin, urlparse
from playwright.async_api import Page

from .base_scraper import BaseScraper
from utils.image_downloader import ImageDownloader
from utils.data_normalizer import DataNormalizer


class ParaisoDoradoScraper(BaseScraper):
    """
    Scraper especializado para el sitio Paraíso Dorado
    Extrae información de propiedades inmobiliarias en Mazatlán
    """
    
    def __init__(self, output_dir: str = "data", headless: bool = True):
        """
        Inicializa el scraper de Paraíso Dorado
        
        Args:
            output_dir: Directorio donde se guardarán los datos
            headless: Si es False, muestra el navegador
        """
        super().__init__(output_dir, headless)
        self.site_name = "paraiso_dorado"
        self.image_downloader = ImageDownloader(str(self.images_dir))
        self.normalizer = DataNormalizer()
    
    def get_selectors(self) -> Dict[str, Any]:
        """
        Selectores CSS específicos de Paraíso Dorado
        
        Returns:
            dict: Diccionario con selectores organizados
        """
        return {
            'titulo': [
                'h1',
                '.property-title',
                '[class*="title"]'
            ],
            'ubicacion': [
                'h1 + div',  # Ubicación suele estar después del h1
                '.property-location',
                '[class*="location"]',
                'text=/.*Mazatlán.*/',
                'text=/.*Sinaloa.*/'
            ],
            'precio': [
                '[class*="price"]',
                '[class*="precio"]',
                'text=/\\$.+MXN/',
                'text=/\\$.+USD/'
            ],
            'estado': [
                '[class*="status"]',
                '[class*="estado"]',
                '.badge',
                '.label',
                'text=/en venta/i',
                'text=/en renta/i'
            ],
            'descripcion': [
                'section:has-text("Descripción")',
                '[class*="description"]',
                '[class*="descripcion"]',
                '.property-description'
            ],
            'agente_nombre': [
                '[class*="agent"] h3',
                '[class*="agent"] h4',
                '.agent-name',
                'text=/Sergio Girón/i'
            ],
            'agente_cargo': [
                'text=/Director/i',
                '.agent-title'
            ],
            'agente_telefono': [
                'a[href*="tel"]',
                '[class*="phone"]',
                '[class*="telefono"]'
            ]
        }
    
    async def extract_custom_data(self, page: Page, data: Dict) -> Dict:
        """
        Extrae datos específicos de Paraíso Dorado
        
        Args:
            page: Página de Playwright
            data: Diccionario con datos ya extraídos
            
        Returns:
            dict: Diccionario actualizado
        """
        # Empresa siempre es Paraíso Dorado
        data['empresa'] = 'Paraíso Dorado'
        
        # Extraer información del terreno
        print("📐 Extrayendo datos del terreno/propiedad...")
        data['terreno'] = await self._extraer_terreno(page)
        
        # Extraer tipo de propiedad
        print("🏠 Extrayendo tipo de propiedad...")
        data['tipo_propiedad'] = await self._extraer_tipo_propiedad(page)
        
        # Extraer características
        print("✨ Extrayendo características...")
        data['caracteristicas'] = await self._extraer_caracteristicas(page)
        
        # Extraer información del agente
        print("👤 Extrayendo información del agente...")
        data['agente'] = await self._extraer_agente(page)
        
        # Extraer y descargar imágenes
        print("🖼️  Extrayendo imágenes...")
        data['imagenes'], data['imagenes_descargadas'] = await self._extraer_imagenes(page, data['url'])
        
        # Normalizar precio
        if data.get('precio'):
            precio_normalizado = self.normalizer.normalizar_precio(data['precio'])
            data['precio_normalizado'] = precio_normalizado
        
        # Extraer ID de propiedad
        property_id = self.normalizer.extraer_id_propiedad(data['url'])
        if property_id:
            data['property_id'] = property_id
        
        return data
    
    async def _extraer_terreno(self, page: Page) -> Dict[str, Any]:
        """Extrae información del terreno"""
        terreno = {}
        
        try:
            page_content = await page.content()
            
            # Patrón 1: "Terreno: 9.33has."
            terreno_match = re.search(r'Terreno:?\s*([\d,.]+)\s*(m[²2]|has?\.?|metros?)', 
                                     page_content, re.IGNORECASE)
            if terreno_match:
                superficie_texto = f"{terreno_match.group(1)} {terreno_match.group(2)}"
                superficie = self.normalizer.normalizar_superficie(superficie_texto)
                if superficie:
                    terreno['superficie'] = superficie
            
            # Patrón 2: Frente (ej: "100 METROS DE FRENTE A LA CARRETERA")
            frente_match = re.search(r'(\d+)\s*m(?:etros?)?\s*de\s*frente', 
                                    page_content, re.IGNORECASE)
            if frente_match:
                terreno['frente'] = f"{frente_match.group(1)} metros"
            
            # Patrón 3: Fondo
            fondo_match = re.search(r'Fondo:?\s*(\d+)\s*metros?', 
                                   page_content, re.IGNORECASE)
            if fondo_match:
                terreno['fondo'] = f"{fondo_match.group(1)} metros"
            
            # Patrón 4: Laguna (ej: "TIENE UNA LAGUNA DE 2'500m²")
            laguna_match = re.search(r'laguna\s+de\s+([\d,\']+)\s*m[²2]?', 
                                    page_content, re.IGNORECASE)
            if laguna_match:
                superficie_laguna = laguna_match.group(1).replace("'", "").replace(",", "")
                terreno['laguna'] = f"{superficie_laguna} m²"
            
            # Patrón 5: Frente a carretera
            if re.search(r'frente\s+a\s+(?:la\s+)?carretera', page_content, re.IGNORECASE):
                terreno['frente_carretera'] = True
            
            if terreno:
                print(f"   Terreno: {terreno}")
        
        except Exception as e:
            print(f"   ⚠ Error extrayendo terreno: {e}")
        
        return terreno
    
    async def _extraer_tipo_propiedad(self, page: Page) -> str:
        """Extrae el tipo de propiedad SOLO de la descripción principal (no sidebar)"""
        try:
            # 🎯 SOLO extraer texto de la sección de descripción principal
            # NO de todo el HTML (para evitar falsos positivos del sidebar)
            descripcion_elem = await page.query_selector('section:has-text("Descripción")')
            
            if not descripcion_elem:
                # Fallback: buscar por selectores alternativos
                descripcion_elem = await page.query_selector('[class*="description"], [class*="descripcion"]')
            
            descripcion_texto = ""
            if descripcion_elem:
                descripcion_texto = await descripcion_elem.text_content()
            
            # Si no hay descripción, usar título + URL
            if not descripcion_texto:
                titulo_elem = await page.query_selector('h1')
                if titulo_elem:
                    descripcion_texto = await titulo_elem.text_content()
            
            # Buscar en el HTML o breadcrumbs
            tipos = {
                'departamento': ['departamento', 'depto', 'DEPARTAMENTO'],  # ⬆️ Departamento PRIMERO
                'terreno_agricola': ['tierra agrícola', 'tierra agricola', 'terreno agrícola', 'terreno agricola', 'AGRICOLA', 'hectáreas de tierra'],
                'casa': ['Casa', 'casa'],
                'condominio': ['Condominio', 'condominio'],
                'terreno': ['Terreno', 'terreno'],
                'edificio': ['Edificio', 'edificio'],
                'local': ['Local', 'local comercial'],
                'bodega': ['Bodega', 'bodega'],
                'lote': ['Lote', 'lote residencial']
            }
            
            # Buscar en descripción + URL
            url_lower = page.url.lower()
            busqueda_texto = (descripcion_texto + " " + url_lower).lower()
            
            # Buscar tipo específico primero (departamento tiene prioridad sobre terreno)
            for tipo, palabras in tipos.items():
                for palabra in palabras:
                    if palabra.lower() in busqueda_texto:
                        tipo_display = tipo.replace('_', ' ').title()
                        print(f"   Tipo: {tipo_display}")
                        return tipo
        
        except Exception as e:
            print(f"   ⚠ Error extrayendo tipo: {e}")
        
        return None
    
    async def _extraer_caracteristicas(self, page: Page) -> Dict[str, Any]:
        """Extrae características SOLO de la descripción principal"""
        caracteristicas = {}
        
        try:
            # 🎯 SOLO extraer texto de la sección de descripción principal
            descripcion_elem = await page.query_selector('section:has-text("Descripción")')
            
            if not descripcion_elem:
                descripcion_elem = await page.query_selector('[class*="description"], [class*="descripcion"]')
            
            descripcion_texto = ""
            if descripcion_elem:
                descripcion_texto = await descripcion_elem.text_content()
            else:
                # Fallback: todo el contenido (si no hay sección específica)
                descripcion_texto = await page.content()
            
            # Buscar patrones comunes SOLO en descripción
            patrones = {
                'agricola': r'agrícola|agricola|tierra agrícola|tierra agricola|AGRICOLA',
                'esquina': r'en esquina|esquinero',
                'cochera': r'cochera|estacionamiento',
                'amueblado': r'amueblado|con muebles',
                'alberca': r'alberca|piscina',
                'jardin': r'jardín|garden',
                'seguridad': r'seguridad 24/7|vigilancia',
                'riego': r'canal de agua|sistema de riego|tubería.*agua',
                'laguna': r'laguna|cuerpo de agua'
            }
            
            for key, patron in patrones.items():
                if re.search(patron, descripcion_texto, re.IGNORECASE):
                    caracteristicas[key] = True
            
            # Buscar recámaras y baños
            recamaras = re.search(r'(\d+)\s*recámaras?', descripcion_texto, re.IGNORECASE)
            if recamaras:
                caracteristicas['recamaras'] = int(recamaras.group(1))
            
            baños = re.search(r'(\d+)\s*baños?', descripcion_texto, re.IGNORECASE)
            if baños:
                caracteristicas['baños'] = int(baños.group(1))
            
            # Buscar cultivos si es agrícola
            if caracteristicas.get('agricola'):
                # Buscar qué se siembra: "se siembra chile, tomate, legumbres y maiz"
                cultivos_match = re.search(r'se\s+siembra\s+([^.]+)', descripcion_texto, re.IGNORECASE)
                if cultivos_match:
                    cultivos_texto = cultivos_match.group(1)
                    caracteristicas['cultivos'] = cultivos_texto.strip()
            
            if caracteristicas:
                print(f"   Características: {list(caracteristicas.keys())}")
        
        except Exception as e:
            print(f"   ⚠ Error extrayendo características: {e}")
        
        return caracteristicas
    
    async def _extraer_agente(self, page: Page) -> Dict[str, str]:
        """Extrae información del agente de bienes raíces"""
        agente = {}
        selectores = self.get_selectors()
        
        try:
            # Nombre del agente
            nombre = await self.extraer_texto(page, selectores['agente_nombre'])
            if nombre:
                agente['nombre'] = nombre
            
            # Cargo
            cargo = await self.extraer_texto(page, selectores['agente_cargo'])
            if cargo:
                agente['cargo'] = cargo
            
            # Teléfono
            telefono_elem = await page.query_selector('a[href*="tel"]')
            if telefono_elem:
                telefono = await telefono_elem.text_content()
                telefono_normalizado = self.normalizer.normalizar_telefono(telefono)
                if telefono_normalizado:
                    agente['telefono'] = telefono_normalizado
            
            if agente:
                print(f"   Agente: {agente.get('nombre', 'N/A')}")
        
        except Exception as e:
            print(f"   ⚠ Error extrayendo agente: {e}")
        
        return agente
    
    async def _extraer_imagenes(self, page: Page, url: str) -> tuple[List[str], List[str]]:
        """
        Extrae y descarga imágenes de la propiedad
        
        Returns:
            tuple: (urls_imagenes, rutas_descargadas)
        """
        urls_imagenes = []
        
        try:
            # Extraer ID de propiedad para filtrar imágenes
            property_id = self.normalizer.extraer_id_propiedad(url)
            
            # Buscar contenedor de galería
            gallery_selectors = [
                '.property-gallery',
                '[class*="gallery"]',
                '[class*="slider"]',
                '[class*="carousel"]',
                '.portada',
                '[class*="portada"]'
            ]
            
            gallery_container = None
            for selector in gallery_selectors:
                try:
                    gallery_container = await page.query_selector(selector)
                    if gallery_container:
                        print(f"   ✓ Galería encontrada: {selector}")
                        break
                except:
                    continue
            
            # Obtener imágenes
            if gallery_container:
                imagenes = await gallery_container.query_selector_all('img')
            else:
                imagenes = await page.query_selector_all('img')
            
            print(f"   📸 Imágenes encontradas: {len(imagenes)}")
            
            # Filtrar y extraer URLs
            for img in imagenes:
                src = await img.get_attribute('src')
                if not src:
                    continue
                
                # Convertir a URL absoluta
                img_url = urljoin(url, src)
                
                # Excluir logos, iconos, etc.
                excluded = ['logo', 'icon', 'avatar', 'user', 'facebook', 
                           'instagram', 'youtube', 'twitter', 'whatsapp']
                
                if any(pattern in img_url.lower() for pattern in excluded):
                    continue
                
                # Si hay ID, filtrar por ID
                if property_id:
                    property_patterns = [
                        f'id{property_id}',
                        f'pro_{property_id}',
                        f'property_{property_id}',
                        f'/{property_id}/'
                    ]
                    
                    if any(pattern in img_url for pattern in property_patterns):
                        if img_url not in urls_imagenes:
                            urls_imagenes.append(img_url)
                else:
                    # Sin ID, incluir todas las imágenes de la galería
                    if gallery_container and img_url not in urls_imagenes:
                        urls_imagenes.append(img_url)
            
            print(f"   ✓ Imágenes válidas: {len(urls_imagenes)}")
            
            # Descargar imágenes en carpeta específica de la propiedad
            imagenes_descargadas = []
            if urls_imagenes:
                # Crear nombre de carpeta basado en el ID de la propiedad
                if property_id:
                    carpeta_propiedad = f"propiedad_{property_id}"
                    prefijo = f"imagen"
                else:
                    carpeta_propiedad = None
                    prefijo = "paraiso_dorado"
                
                imagenes_descargadas = await self.image_downloader.descargar_multiples(
                    urls_imagenes, 
                    prefijo=prefijo,
                    carpeta_propiedad=carpeta_propiedad
                )
        
        except Exception as e:
            print(f"   ⚠ Error extrayendo imágenes: {e}")
        
        return urls_imagenes, imagenes_descargadas


async def main():
    """Función de prueba"""
    # URL de ejemplo
    url = "https://paraisodorado.com.mx/es/propiedad/oportunidad-de-excelente-inversion-en-el-walamo-id153"
    
    # Crear scraper
    scraper = ParaisoDoradoScraper(output_dir="data")
    
    # Scrapear
    resultado = await scraper.extraer_informacion(url)
    
    print("\n✅ Prueba completada!")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
