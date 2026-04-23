"""
Scraper de Propiedades Inmobiliarias con Playwright
Extrae información detallada de propiedades en venta
"""

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright
import aiohttp


class PropiedadScraper:
    def __init__(self, output_dir="data"):
        """
        Inicializa el scraper
        
        Args:
            output_dir: Directorio donde se guardarán los datos e imágenes
        """
        self.output_dir = Path(output_dir)
        self.images_dir = self.output_dir / "imagenes"
        self.json_dir = self.output_dir / "json"
        
        # Crear directorios si no existen
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.json_dir.mkdir(parents=True, exist_ok=True)
    
    async def descargar_imagen(self, session, url, nombre_archivo):
        """
        Descarga una imagen de forma asíncrona
        
        Args:
            session: Sesión aiohttp
            url: URL de la imagen
            nombre_archivo: Nombre del archivo a guardar
        """
        try:
            async with session.get(url, timeout=30) as response:
                if response.status == 200:
                    content = await response.read()
                    filepath = self.images_dir / nombre_archivo
                    with open(filepath, 'wb') as f:
                        f.write(content)
                    print(f"   ✓ Imagen descargada: {nombre_archivo}")
                    return str(filepath)
                else:
                    print(f"   ✗ Error al descargar {url}: Status {response.status}")
                    return None
        except Exception as e:
            print(f"   ✗ Error al descargar {url}: {str(e)}")
            return None
    
    async def extraer_informacion(self, url):
        """
        Extrae toda la información de una propiedad
        
        Args:
            url: URL de la propiedad a scrapear
            
        Returns:
            dict: Diccionario con toda la información extraída
        """
        print(f"\n{'='*80}")
        print(f"SCRAPEANDO: {url}")
        print(f"{'='*80}\n")
        
        async with async_playwright() as p:
            # Lanzar navegador
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            )
            page = await context.new_page()
            
            try:
                # Navegar a la página
                print("⏳ Cargando página...")
                await page.goto(url, wait_until='networkidle', timeout=60000)
                print("✓ Página cargada\n")
                
                # Esperar a que el contenido principal cargue
                await page.wait_for_selector('body', timeout=10000)
                await asyncio.sleep(2)  # Dar tiempo para contenido dinámico
                
                # ==================================================
                # EXTRAER DATOS
                # ==================================================
                
                data = {
                    'url': url,
                    'fecha_scraping': datetime.now().isoformat(),
                    'empresa': None,
                    'titulo': None,
                    'ubicacion': None,
                    'precio': None,
                    'moneda': None,
                    'estado': None,
                    'terreno': {},
                    'descripcion': None,
                    'agente': {},
                    'imagenes': [],
                    'imagenes_descargadas': []
                }
                
                # 1. EMPRESA
                print("📊 Extrayendo información de la empresa...")
                try:
                    # Logo o nombre en el header
                    empresa_elem = await page.query_selector('header img[alt], .logo, header a')
                    if empresa_elem:
                        empresa_alt = await empresa_elem.get_attribute('alt')
                        if empresa_alt:
                            data['empresa'] = empresa_alt
                    
                    # Si no se encontró, buscar en footer o meta
                    if not data['empresa']:
                        footer_text = await page.query_selector('footer')
                        if footer_text:
                            text = await footer_text.text_content()
                            # Buscar copyright o nombre
                            if 'paraiso' in text.lower() or 'dorado' in text.lower():
                                data['empresa'] = 'Paraíso Dorado'
                    
                    print(f"   Empresa: {data['empresa']}")
                except Exception as e:
                    print(f"   ⚠ Error extrayendo empresa: {e}")
                
                # 2. TÍTULO DE LA PROPIEDAD
                print("\n📝 Extrayendo título...")
                try:
                    # Buscar el título principal
                    titulo_selectors = [
                        'h1',
                        '.property-title',
                        '[class*="title"]'
                    ]
                    for selector in titulo_selectors:
                        titulo = await page.query_selector(selector)
                        if titulo:
                            data['titulo'] = (await titulo.text_content()).strip()
                            break
                    print(f"   Título: {data['titulo']}")
                except Exception as e:
                    print(f"   ⚠ Error extrayendo título: {e}")
                
                # 3. UBICACIÓN
                print("\n📍 Extrayendo ubicación...")
                try:
                    # Buscar por icono de ubicación o texto específico
                    ubicacion_selectors = [
                        'text=/.*Mazatlán.*/',
                        'text=/.*Sinaloa.*/',
                        '[class*="location"]',
                        '[class*="ubicacion"]'
                    ]
                    
                    # Intentar extraer de la cabecera donde dice "PLAYA SUR, Mazatlán, Sinaloa"
                    ubicacion_elem = await page.query_selector('.property-location, [class*="location"], h1 + div, header div')
                    if not ubicacion_elem:
                        # Buscar después del título
                        ubicacion_elem = await page.query_selector('h1 ~ div, h1 ~ p')
                    
                    if ubicacion_elem:
                        ubicacion_text = await ubicacion_elem.text_content()
                        if 'mazatlán' in ubicacion_text.lower() or 'sinaloa' in ubicacion_text.lower():
                            data['ubicacion'] = ubicacion_text.strip()
                    
                    print(f"   Ubicación: {data['ubicacion']}")
                except Exception as e:
                    print(f"   ⚠ Error extrayendo ubicación: {e}")
                
                # 4. PRECIO
                print("\n💰 Extrayendo precio...")
                try:
                    # Estrategia 1: Buscar elementos con clase relacionada a precio
                    precio_elem = await page.query_selector('[class*=price], [class*=precio]')
                    
                    # Estrategia 2: Buscar texto que contenga símbolo de dinero
                    if not precio_elem:
                        # Buscar todos los elementos que contengan $ seguido de números
                        all_text = await page.content()
                        precio_match = re.search(r'\$([0-9,]+(?:\.[0-9]{2})?)\s*(MXN|USD|pesos|dólares)?', all_text, re.IGNORECASE)
                        if precio_match:
                            data['precio'] = '$' + precio_match.group(1)
                            if precio_match.group(2):
                                moneda_text = precio_match.group(2).upper()
                                if 'MXN' in moneda_text or 'PESOS' in moneda_text:
                                    data['moneda'] = 'MXN'
                                    data['precio'] = data['precio'] + ' MXN'
                                elif 'USD' in moneda_text or 'DÓLARES' in moneda_text:
                                    data['moneda'] = 'USD'
                                    data['precio'] = data['precio'] + ' USD'
                    
                    # Si encontramos elemento, extraer su texto
                    if precio_elem:
                        precio_text = await precio_elem.text_content()
                        precio_text = precio_text.strip()
                        
                        # Extraer moneda
                        if 'MXN' in precio_text or 'pesos' in precio_text.lower():
                            data['moneda'] = 'MXN'
                        elif 'USD' in precio_text or 'dólares' in precio_text.lower():
                            data['moneda'] = 'USD'
                        
                        # Limpiar y extraer solo el precio
                        data['precio'] = precio_text
                    
                    print(f"   Precio: {data['precio']}")
                    print(f"   Moneda: {data['moneda']}")
                except Exception as e:
                    print(f"   ⚠ Error extrayendo precio: {e}")
                
                # 5. ESTADO (En Venta, En Renta, etc.)
                print("\n🏷️  Extrayendo estado...")
                try:
                    # Buscar badges o etiquetas de estado
                    estado_elem = await page.query_selector('[class*=status], [class*=estado], .badge, .label')
                    if estado_elem:
                        data['estado'] = (await estado_elem.text_content()).strip()
                    
                    # Si no se encontró, buscar por texto común
                    if not data['estado']:
                        # Buscar en el contenido de la página
                        page_text = await page.content()
                        estado_match = re.search(r'(EN VENTA|EN RENTA|VENDIDO|RENTADO|PREVENTA)', page_text, re.IGNORECASE)
                        if estado_match:
                            data['estado'] = estado_match.group(1).upper()
                    
                    print(f"   Estado: {data['estado']}")
                except Exception as e:
                    print(f"   ⚠ Error extrayendo estado: {e}")
                
                # 6. DATOS DEL TERRENO
                print("\n📐 Extrayendo datos del terreno...")
                try:
                    # Buscar sección de descripción que contenga datos del terreno
                    terreno_section = await page.query_selector('text=/Terreno:/i')
                    if terreno_section:
                        # Obtener el contenedor padre
                        parent = await terreno_section.evaluate('el => el.closest("div, section")')
                        
                    # Buscar patrones específicos
                    page_content = await page.content()
                    
                    # Superficie
                    superficie_match = re.search(r'Terreno:?\s*(\d+)\s*m[²2]', page_content, re.IGNORECASE)
                    if superficie_match:
                        data['terreno']['superficie'] = superficie_match.group(1) + ' m²'
                    
                    # Frente
                    frente_match = re.search(r'Frente:?\s*(\d+)\s*metros?', page_content, re.IGNORECASE)
                    if frente_match:
                        data['terreno']['frente'] = frente_match.group(1) + ' metros'
                    
                    # Fondo
                    fondo_match = re.search(r'Fondo:?\s*(\d+)\s*metros?', page_content, re.IGNORECASE)
                    if fondo_match:
                        data['terreno']['fondo'] = fondo_match.group(1) + ' metros'
                    
                    print(f"   Terreno: {json.dumps(data['terreno'], indent=4, ensure_ascii=False)}")
                except Exception as e:
                    print(f"   ⚠ Error extrayendo datos del terreno: {e}")
                
                # 7. DESCRIPCIÓN
                print("\n📄 Extrayendo descripción...")
                try:
                    # Buscar la sección de descripción
                    descripcion_selectors = [
                        'section:has-text("Descripción")',
                        '[class*="description"]',
                        '[class*="descripcion"]'
                    ]
                    
                    for selector in descripcion_selectors:
                        try:
                            desc_section = await page.query_selector(selector)
                            if desc_section:
                                # Obtener todo el texto de esa sección
                                desc_text = await desc_section.text_content()
                                # Limpiar el texto (quitar "Descripción" del inicio si existe)
                                desc_text = desc_text.replace('Descripción', '').strip()
                                if len(desc_text) > 50:  # Verificar que no sea solo un título
                                    data['descripcion'] = desc_text
                                    break
                        except:
                            continue
                    
                    if data['descripcion']:
                        preview = data['descripcion'][:200] + '...' if len(data['descripcion']) > 200 else data['descripcion']
                        print(f"   Descripción: {preview}")
                except Exception as e:
                    print(f"   ⚠ Error extrayendo descripción: {e}")
                
                # 8. INFORMACIÓN DEL AGENTE
                print("\n👤 Extrayendo información del agente...")
                try:
                    # Nombre del agente - buscar en elementos de agente o nombres comunes
                    agente_selectors = [
                        '[class*=agent] h3',
                        '[class*=agent] h4',
                        '[class*=agent] .name',
                        '.agent-name',
                        'text=Sergio Girón'
                    ]
                    
                    for selector in agente_selectors:
                        try:
                            agente_nombre = await page.query_selector(selector)
                            if agente_nombre:
                                nombre_text = (await agente_nombre.text_content()).strip()
                                if nombre_text and len(nombre_text) > 2:
                                    data['agente']['nombre'] = nombre_text
                                    break
                        except:
                            continue
                    
                    # Si no se encontró, buscar por patrón en el HTML
                    if not data['agente'].get('nombre'):
                        page_content = await page.content()
                        # Buscar "Sergio Girón" o similar
                        nombre_match = re.search(r'Sergio Girón|([A-ZÁÉÍÓÚ][a-záéíóúñ]+\s+[A-ZÁÉÍÓÚ][a-záéíóúñ]+)(?=\s*Director)', page_content)
                        if nombre_match:
                            data['agente']['nombre'] = nombre_match.group(0) if 'Sergio' in nombre_match.group(0) else nombre_match.group(1)
                    
                    # Cargo
                    try:
                        cargo = await page.query_selector('text=Director')
                        if cargo:
                            data['agente']['cargo'] = (await cargo.text_content()).strip()
                    except:
                        # Buscar en el HTML
                        if 'Director' in page_content:
                            data['agente']['cargo'] = 'Director'
                    
                    # Teléfono
                    try:
                        telefono = await page.query_selector('a[href*=tel]')
                        if telefono:
                            tel_text = await telefono.text_content()
                            data['agente']['telefono'] = tel_text.strip()
                        else:
                            # Buscar patrón de teléfono en el contenido
                            tel_match = re.search(r'\(?\d{3}\)?[-\s]?\d{3}[-\s]?\d{4}', page_content)
                            if tel_match:
                                data['agente']['telefono'] = tel_match.group(0)
                    except:
                        pass
                    
                    print(f"   Agente: {json.dumps(data['agente'], indent=4, ensure_ascii=False)}")
                except Exception as e:
                    print(f"   ⚠ Error extrayendo información del agente: {e}")
                
                # 9. IMÁGENES (solo de la galería de la propiedad)
                print("\n🖼️  Extrayendo imágenes de la galería...")
                try:
                    # Extraer ID de la propiedad desde la URL
                    property_id_match = re.search(r'id(\d+)', url)
                    property_id = property_id_match.group(1) if property_id_match else None
                    
                    if property_id:
                        print(f"   ℹ️  ID de propiedad detectado: {property_id}")
                    
                    # Estrategia 1: Buscar el contenedor principal de la galería/carrusel
                    gallery_selectors = [
                        '.property-gallery',
                        '[class*=gallery]',
                        '[class*=slider]',
                        '[class*=carousel]',
                        '.property-images',
                        '[class*=property-image]',
                        '.portada',  # Algunos sitios usan "portada"
                        '.main-image'
                    ]
                    
                    gallery_container = None
                    for selector in gallery_selectors:
                        try:
                            gallery_container = await page.query_selector(selector)
                            if gallery_container:
                                print(f"   ✓ Contenedor de galería encontrado: {selector}")
                                break
                        except:
                            continue
                    
                    # Si encontramos el contenedor, extraer solo sus imágenes
                    if gallery_container:
                        imagenes = await gallery_container.query_selector_all('img')
                        print(f"   ℹ️  Imágenes en el contenedor de galería: {len(imagenes)}")
                    else:
                        # Si no hay contenedor, buscar todas las imágenes
                        print("   ⚠ Contenedor de galería no encontrado, usando filtrado inteligente")
                        imagenes = await page.query_selector_all('img')
                    
                    # Filtrar y extraer URLs
                    for idx, img in enumerate(imagenes):
                        src = await img.get_attribute('src')
                        if src:
                            # Convertir URL relativa a absoluta
                            img_url = urljoin(url, src)
                            
                            # Excluir explícitamente logos, iconos, mapas, etc.
                            excluded_patterns = [
                                'logo',
                                'icon',
                                'avatar',
                                'user',
                                'tile.openstreetmap',
                                'leaflet',
                                'marker',
                                'facebook',
                                'instagram',
                                'youtube',
                                'twitter'
                            ]
                            
                            # Si contiene patrones excluidos, saltar
                            if any(pattern in img_url.lower() for pattern in excluded_patterns):
                                continue
                            
                            # Filtrar por ID de propiedad si lo tenemos
                            if property_id:
                                # Solo incluir imágenes que contengan el ID específico
                                # Buscar patrones como: pro_273_, id273_, property_273_, etc.
                                property_patterns = [
                                    f'pro_{property_id}_',
                                    f'pro_{property_id}.',
                                    f'id{property_id}_',
                                    f'property_{property_id}_',
                                    f'propiedad_{property_id}_',
                                    f'/{property_id}/'
                                ]
                                
                                if any(pattern in img_url for pattern in property_patterns):
                                    if img_url not in data['imagenes']:
                                        data['imagenes'].append(img_url)
                                        print(f"   ✓ Imagen válida: {img_url.split('/')[-1]}")
                            else:
                                # Si no hay ID, usar filtrado por contenedor
                                if gallery_container:
                                    if img_url not in data['imagenes']:
                                        data['imagenes'].append(img_url)
                                else:
                                    # Filtrar por patrón de propiedades pero más estricto
                                    if 'properties' in img_url.lower() or 'pro_' in img_url.lower():
                                        if 'thumb' not in img_url.lower() and img_url not in data['imagenes']:
                                            data['imagenes'].append(img_url)
                    
                    # Si no se encontraron imágenes, avisar
                    if len(data['imagenes']) == 0:
                        print("   ⚠ No se encontraron imágenes de la propiedad")
                    else:
                        print(f"   ✓ Encontradas {len(data['imagenes'])} imágenes de la propiedad")
                    
                    # Descargar imágenes
                    if data['imagenes']:
                        print("\n📥 Descargando imágenes...")
                        async with aiohttp.ClientSession() as session:
                            tasks = []
                            for idx, img_url in enumerate(data['imagenes'], 1):
                                # Generar nombre de archivo único
                                ext = os.path.splitext(urlparse(img_url).path)[1] or '.jpg'
                                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                                nombre_archivo = f"propiedad_{timestamp}_{idx}{ext}"
                                
                                tasks.append(self.descargar_imagen(session, img_url, nombre_archivo))
                            
                            # Descargar todas en paralelo
                            resultados = await asyncio.gather(*tasks)
                            data['imagenes_descargadas'] = [r for r in resultados if r]
                            
                        print(f"\n   ✓ {len(data['imagenes_descargadas'])} imágenes descargadas exitosamente")
                
                except Exception as e:
                    print(f"   ⚠ Error procesando imágenes: {e}")
                
                # ==================================================
                # GUARDAR DATOS
                # ==================================================
                
                print(f"\n{'='*80}")
                print("RESUMEN DE DATOS EXTRAÍDOS")
                print(f"{'='*80}\n")
                print(json.dumps(data, indent=2, ensure_ascii=False))
                
                # Guardar JSON
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                json_filename = f"propiedad_{timestamp}.json"
                json_path = self.json_dir / json_filename
                
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                
                print(f"\n✅ Datos guardados en: {json_path}")
                print(f"✅ Imágenes guardadas en: {self.images_dir}")
                
                return data
                
            except Exception as e:
                print(f"\n❌ Error durante el scraping: {str(e)}")
                raise
            
            finally:
                await browser.close()


async def main():
    """Función principal"""
    
    # URL de ejemplo
    url = "https://paraisodorado.com.mx/es/propiedad/porpiedad-en-playa-sur-id273"
    
    # Crear scraper
    scraper = PropiedadScraper(output_dir="data")
    
    # Scrapear
    resultado = await scraper.extraer_informacion(url)
    
    print(f"\n{'='*80}")
    print("✅ SCRAPING COMPLETADO EXITOSAMENTE")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(main())

