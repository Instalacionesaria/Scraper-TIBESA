"""
Scraper de Listados de Inmuebles24
Extrae URLs de todas las propiedades de una página de resultados
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright


class ListadosInmuebles24Scraper:
    def __init__(self, output_dir="data", headless=True):
        """
        Inicializa el scraper de listados
        
        Args:
            output_dir: Directorio donde se guardarán los datos
            headless: Si es False, muestra el navegador (útil para debugging)
        """
        self.output_dir = Path(output_dir)
        self.json_dir = self.output_dir / "json"
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
    
    async def extraer_urls_listado(self, url_listado):
        """
        Extrae todas las URLs de propiedades de una página de listados
        
        Args:
            url_listado: URL de la página de resultados de inmuebles24
            
        Returns:
            list: Lista de URLs de propiedades individuales
        """
        print(f"\n{'='*80}")
        print(f"📋 SCRAPEANDO LISTADO: {url_listado}")
        print(f"{'='*80}\n")
        
        async with async_playwright() as p:
            # Lanzar navegador con configuración para evitar detección
            browser = await p.chromium.launch(
                headless=self.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox'
                ]
            )
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='es-MX',
                timezone_id='America/Mexico_City',
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'es-MX,es;q=0.9,en;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
            )
            
            # Ocultar que es Playwright
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            page = await context.new_page()
            
            try:
                # Navegar a la página de listados
                print("⏳ Cargando página de listados...")
                await page.goto(url_listado, wait_until='networkidle', timeout=60000)
                print("✓ Página cargada\n")
                
                # Esperar a que el contenido cargue
                await page.wait_for_selector('body', timeout=10000)
                
                # Esperar a que Cloudflare complete su verificación (si existe)
                print("⏳ Esperando verificación de Cloudflare (si aplica)...")
                try:
                    # Esperar a que desaparezca el mensaje de Cloudflare
                    await page.wait_for_function(
                        "document.title !== 'Just a moment...' && !document.body.textContent.includes('Verify you are human')",
                        timeout=30000
                    )
                    print("✓ Verificación de Cloudflare completada")
                except:
                    print("⚠ Cloudflare puede estar activo, continuando...")
                
                # Esperar más tiempo para contenido dinámico
                print("⏳ Esperando carga de contenido dinámico...")
                await asyncio.sleep(8)  # Aumentado a 8 segundos para Cloudflare
                
                # Verificar si estamos en página de Cloudflare
                page_title = await page.title()
                page_content = await page.content()
                
                if "Just a moment" in page_title or "Verify you are human" in page_content:
                    print("🛡️  Cloudflare detectado, esperando verificación...")
                    # Esperar hasta 30 segundos a que Cloudflare termine
                    for i in range(30):
                        await asyncio.sleep(1)
                        current_title = await page.title()
                        if "Just a moment" not in current_title:
                            print(f"✓ Cloudflare completado después de {i+1} segundos")
                            break
                    else:
                        print("⚠ Cloudflare puede estar bloqueando, continuando de todas formas...")
                
                # Hacer scroll para cargar contenido lazy-loaded
                print("📜 Haciendo scroll para cargar contenido...")
                await page.evaluate("""
                    async () => {
                        await new Promise((resolve) => {
                            let totalHeight = 0;
                            const distance = 100;
                            const timer = setInterval(() => {
                                const scrollHeight = document.body.scrollHeight;
                                window.scrollBy(0, distance);
                                totalHeight += distance;
                                
                                if(totalHeight >= scrollHeight || totalHeight > 5000){
                                    clearInterval(timer);
                                    resolve();
                                }
                            }, 100);
                        });
                    }
                """)
                
                # Esperar un poco más después del scroll
                await asyncio.sleep(5)
                
                # Intentar esperar a elementos específicos de inmuebles24
                try:
                    # Esperar a que aparezcan cards o listados
                    await page.wait_for_selector('article, [class*="posting"], [class*="listing"], [class*="card"], [data-posting-id], [class*="property"]', timeout=15000)
                    print("✓ Contenido de propiedades detectado")
                except:
                    print("⚠ No se detectaron elementos específicos, continuando...")
                
                print("")
                
                # Extraer número total de resultados
                print("📊 Extrayendo información del listado...")
                total_resultados = None
                try:
                    # Buscar texto como "262 Terrenos en venta"
                    page_text = await page.content()
                    import re
                    
                    # Múltiples patrones para encontrar el total
                    patrones = [
                        r'(\d+)\s+Terrenos?\s+en\s+venta',
                        r'(\d+)\s+resultados?',
                        r'(\d+)\s+propiedades?',
                        r'(\d+)\s+inmuebles?',
                        r'encontramos\s+(\d+)',
                        r'mostrando\s+(\d+)',
                        r'total[:\s]+(\d+)'
                    ]
                    
                    for patron in patrones:
                        resultado_match = re.search(patron, page_text, re.IGNORECASE)
                        if resultado_match:
                            total_resultados = int(resultado_match.group(1))
                            print(f"   ✓ Total de propiedades encontradas: {total_resultados}")
                            break
                    
                    # Si no se encontró, intentar buscar en elementos específicos
                    if not total_resultados:
                        try:
                            total_elem = await page.query_selector('h1, .results-count, [class*="count"], [class*="total"]')
                            if total_elem:
                                texto = await total_elem.text_content()
                                match = re.search(r'(\d+)', texto)
                                if match:
                                    total_resultados = int(match.group(1))
                                    print(f"   ✓ Total extraído de elemento: {total_resultados}")
                        except:
                            pass
                            
                except Exception as e:
                    print(f"   ⚠ No se pudo extraer el total: {e}")
                
                # Extraer URLs de propiedades
                print("\n🔗 Extrayendo URLs de propiedades...")
                urls_propiedades = []
                enlaces_encontrados = set()  # Usar set para evitar duplicados
                
                # Estrategia 0: Extraer desde HTML completo usando regex
                print("   🔍 Extrayendo URLs desde HTML completo...")
                try:
                    html_content = await page.content()
                    import re
                    # Buscar patrones de URLs de inmuebles24 (patrón real)
                    url_patterns = [
                        r'https?://[^"\s]*inmuebles24\.com/propiedades/[^"\s]+\.html[^"\s]*',
                        r'/propiedades/[^"\s\'"]+\.html[^"\s\'"]*',
                        r'https?://[^"\s]*inmuebles24\.com/inmueble/[^"\s]+',
                        r'https?://[^"\s]*inmuebles24\.com/terreno/[^"\s]+',
                        r'/inmueble/[^"\s\'"]+',
                        r'/terreno/[^"\s\'"]+',
                    ]
                    
                    for pattern in url_patterns:
                        matches = re.findall(pattern, html_content)
                        for match in matches:
                            if match.startswith('/'):
                                url_completa = urljoin(url_listado, match)
                            else:
                                url_completa = match
                            
                            # Limpiar parámetros de query string (mantener solo la URL base)
                            if '?' in url_completa:
                                url_completa = url_completa.split('?')[0]
                            
                            if 'inmuebles24.com' in url_completa and any(p in url_completa for p in ['/propiedades/', '/inmueble/', '/terreno/']):
                                if not any(excluded in url_completa.lower() for excluded in ['/buscar', '/filtros', '/mapa', 'javascript:', '#']):
                                    enlaces_encontrados.add(url_completa)
                    
                    if enlaces_encontrados:
                        print(f"   ✓ Encontradas {len(enlaces_encontrados)} URLs desde HTML")
                except Exception as e:
                    print(f"   ⚠ Error extrayendo desde HTML: {e}")
                
                # Estrategia 1: Buscar enlaces en cards de propiedades
                # Los enlaces suelen estar en elementos <a> dentro de las cards
                selectores_enlaces = [
                    'a[href*="/propiedades/"]',      # Patrón real: /propiedades/tipo/slug-id.html
                    'a[href*="inmuebles24.com/propiedades"]',  # URL completa
                    'a[href*="/inmueble/"]',          # Patrón alternativo
                    'a[href*="/terreno/"]',          # Patrón alternativo
                    'a[href*="/propiedad/"]',        # Patrón alternativo
                    'a[href*="inmuebles24.com/inmueble"]',  # URL completa alternativa
                    '.posting-item a',               # Clase común en inmuebles24
                    '[data-posting-id] a',           # Por data attribute
                    'article a',                     # En elementos article
                    '.card a',                       # En cards
                    '[class*="posting"] a',          # Cualquier clase con "posting"
                    '[class*="listing"] a',          # Clase listing
                    '[class*="property"] a',         # Clase property
                    'h2 a',                          # Enlaces en títulos h2
                    'h3 a',                          # Enlaces en títulos h3
                    '.title a',                      # Enlaces en títulos
                    '[class*="title"] a',            # Cualquier clase con title
                    '[data-to]',                     # Atributo data-to
                    '[data-href]',                   # Atributo data-href
                    '[data-url]'                     # Atributo data-url
                ]
                
                for selector in selectores_enlaces:
                    try:
                        enlaces = await page.query_selector_all(selector)
                        print(f"   🔍 Probando selector '{selector}': {len(enlaces)} enlaces encontrados")
                        
                        for enlace in enlaces:
                            # Buscar en href primero
                            href = await enlace.get_attribute('href')
                            
                            # Si no hay href, buscar en atributos data-*
                            if not href:
                                href = await enlace.get_attribute('data-href') or \
                                       await enlace.get_attribute('data-url') or \
                                       await enlace.get_attribute('data-to') or \
                                       await enlace.get_attribute('data-link')
                            
                            if href:
                                # Convertir URL relativa a absoluta
                                url_completa = urljoin(url_listado, href)
                                
                                # Limpiar parámetros de query string (mantener solo la URL base)
                                if '?' in url_completa:
                                    url_completa = url_completa.split('?')[0]
                                
                                # Filtrar solo URLs de propiedades (no filtros, búsquedas, etc.)
                                if any(pattern in url_completa.lower() for pattern in [
                                    '/propiedades/',      # Patrón real de inmuebles24
                                    '/inmueble/',
                                    '/terreno/',
                                    '/propiedad/',
                                    '/casa/',
                                    '/departamento/'
                                ]):
                                    # Excluir URLs de búsqueda o filtros
                                    if not any(excluded in url_completa.lower() for excluded in [
                                        '/buscar',
                                        '/filtros',
                                        '/mapa',
                                        '/ordenar',
                                        'javascript:',
                                        '#'
                                    ]):
                                        enlaces_encontrados.add(url_completa)
                    except Exception as e:
                        print(f"   ⚠ Error con selector '{selector}': {e}")
                        continue
                
                urls_propiedades = list(enlaces_encontrados)
                print(f"\n   ✓ URLs únicas encontradas: {len(urls_propiedades)}")
                
                # Guardar HTML para debugging si no encontramos URLs
                if len(urls_propiedades) == 0:
                    print("\n   🔍 Guardando HTML para debugging...")
                    try:
                        html_debug = await page.content()
                        debug_path = self.json_dir / f"debug_html_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
                        with open(debug_path, 'w', encoding='utf-8') as f:
                            f.write(html_debug)
                        print(f"   ✓ HTML guardado en: {debug_path}")
                    except Exception as e:
                        print(f"   ⚠ Error guardando HTML: {e}")
                
                # Si no encontramos suficientes, intentar otra estrategia
                if len(urls_propiedades) < (total_resultados or 10):
                    print("\n   🔄 Intentando estrategia alternativa...")
                    
                    # Buscar todos los enlaces y filtrar
                    todos_enlaces = await page.query_selector_all('a[href]')
                    print(f"   ℹ️  Total de enlaces en la página: {len(todos_enlaces)}")
                    
                    # También buscar elementos con data attributes
                    elementos_data = await page.query_selector_all('[data-posting-id], [data-id], [data-url], [data-href]')
                    print(f"   ℹ️  Elementos con data attributes: {len(elementos_data)}")
                    
                    for enlace in todos_enlaces:
                        href = await enlace.get_attribute('href')
                        if href:
                            url_completa = urljoin(url_listado, href)
                            
                            # Filtrar por dominio de inmuebles24 y patrón de propiedad
                            if 'inmuebles24.com' in url_completa:
                                if any(pattern in url_completa.lower() for pattern in [
                                    '/propiedades/',      # Patrón real de inmuebles24
                                    '/inmueble/',
                                    '/terreno/',
                                    '/propiedad/'
                                ]):
                                    # Excluir URLs de búsqueda o filtros
                                    if not any(excluded in url_completa.lower() for excluded in [
                                        '/buscar',
                                        '/filtros',
                                        '/mapa',
                                        '/ordenar',
                                        'javascript:',
                                        '#'
                                    ]):
                                        if url_completa not in enlaces_encontrados:
                                            enlaces_encontrados.add(url_completa)
                    
                    urls_propiedades = list(enlaces_encontrados)
                    print(f"   ✓ URLs encontradas (método alternativo): {len(urls_propiedades)}")
                
                # Manejar paginación si existe
                print("\n📄 Verificando paginación...")
                urls_paginas = await self._obtener_urls_paginacion(page, url_listado)
                
                if urls_paginas:
                    print(f"   ✓ Encontradas {len(urls_paginas)} páginas adicionales")
                    print("   🔄 Scrapeando páginas adicionales...")
                    
                    for idx, url_pagina in enumerate(urls_paginas[:5], 1):  # Limitar a 5 páginas para prueba
                        print(f"\n   📄 Página {idx + 1}/{len(urls_paginas)}: {url_pagina}")
                        await page.goto(url_pagina, wait_until='networkidle', timeout=60000)
                        await asyncio.sleep(2)
                        
                        # Extraer URLs de esta página
                        enlaces_pagina = await page.query_selector_all('a[href*="/propiedades/"], a[href*="/inmueble/"], a[href*="/terreno/"]')
                        for enlace in enlaces_pagina:
                            href = await enlace.get_attribute('href')
                            if href:
                                url_completa = urljoin(url_listado, href)
                                # Limpiar parámetros de query string
                                if '?' in url_completa:
                                    url_completa = url_completa.split('?')[0]
                                if url_completa not in enlaces_encontrados:
                                    enlaces_encontrados.add(url_completa)
                    
                    urls_propiedades = list(enlaces_encontrados)
                    print(f"\n   ✓ Total de URLs después de paginación: {len(urls_propiedades)}")
                
                # Guardar resultados
                resultado = {
                    'url_listado': url_listado,
                    'fecha_scraping': datetime.now().isoformat(),
                    'total_resultados_esperados': total_resultados,
                    'urls_encontradas': len(urls_propiedades),
                    'urls': urls_propiedades
                }
                
                # Guardar JSON
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                json_filename = f"listado_inmuebles24_{timestamp}.json"
                json_path = self.json_dir / json_filename
                
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(resultado, f, indent=2, ensure_ascii=False)
                
                print(f"\n{'='*80}")
                print("✅ EXTRACCIÓN COMPLETADA")
                print(f"{'='*80}\n")
                print(f"📊 RESUMEN:")
                print(f"   • Total esperado: {total_resultados or 'N/A'}")
                print(f"   • URLs encontradas: {len(urls_propiedades)}")
                print(f"   • Archivo guardado: {json_path}")
                print(f"\n🔗 Primeras 5 URLs:")
                for i, url in enumerate(urls_propiedades[:5], 1):
                    print(f"   {i}. {url}")
                
                return resultado
                
            except Exception as e:
                print(f"\n❌ Error durante el scraping: {str(e)}")
                import traceback
                traceback.print_exc()
                raise
            
            finally:
                await browser.close()
    
    async def _obtener_urls_paginacion(self, page, url_base):
        """
        Obtiene URLs de páginas adicionales si existe paginación
        
        Args:
            page: Página de Playwright
            url_base: URL base del listado
            
        Returns:
            list: Lista de URLs de páginas adicionales
        """
        urls_paginas = []
        
        try:
            # Buscar botones de paginación
            selectores_paginacion = [
                'a[href*="pagina"]',
                'a[href*="page"]',
                '.pagination a',
                '[class*="pagination"] a',
                '.pager a',
                '[class*="pager"] a'
            ]
            
            for selector in selectores_paginacion:
                try:
                    enlaces = await page.query_selector_all(selector)
                    for enlace in enlaces:
                        href = await enlace.get_attribute('href')
                        if href:
                            url_completa = urljoin(url_base, href)
                            if url_completa not in urls_paginas and url_completa != url_base:
                                urls_paginas.append(url_completa)
                except:
                    continue
            
            # También buscar números de página
            try:
                numeros_pagina = await page.query_selector_all('[class*="page"]:not([class*="current"])')
                for num in numeros_pagina:
                    href = await num.get_attribute('href')
                    if href:
                        url_completa = urljoin(url_base, href)
                        if url_completa not in urls_paginas:
                            urls_paginas.append(url_completa)
            except:
                pass
            
        except Exception as e:
            print(f"   ⚠ Error obteniendo paginación: {e}")
        
        return urls_paginas


async def main():
    """Función principal"""
    
    # URL de ejemplo - reemplaza con la URL real de inmuebles24
    # Ejemplo: "https://www.inmuebles24.com/terrenos-en-venta-en-mazatlan-sinaloa.html"
    url_listado = input("Ingresa la URL del listado de inmuebles24: ").strip()
    
    if not url_listado:
        print("❌ URL no proporcionada")
        return
    
    # Crear scraper
    scraper = ListadosInmuebles24Scraper(output_dir="data")
    
    # Scrapear
    resultado = await scraper.extraer_urls_listado(url_listado)
    
    print(f"\n✅ Proceso completado!")
    print(f"📁 Archivo guardado en: data/json/listado_inmuebles24_*.json")


if __name__ == "__main__":
    asyncio.run(main())

