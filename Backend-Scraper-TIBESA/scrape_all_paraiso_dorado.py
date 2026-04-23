"""
Script para scrapear TODOS los inmuebles de Paraíso Dorado
Navega el sitio completo y extrae información de cada propiedad
"""

import asyncio
import sys
from pathlib import Path
from typing import List, Dict
from datetime import datetime
import json

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent))

from scrapers.paraiso_dorado import ParaisoDoradoScraper
from utils.agente_propiedades import procesar_propiedad_con_llm
from playwright.async_api import async_playwright


class ParaisoDoradoBulkScraper:
    """
    Scraper masivo para todas las propiedades de Paraíso Dorado
    """
    
    def __init__(self, output_dir: str = "data", headless: bool = True, usar_llm: bool = True):
        """
        Inicializa el scraper masivo

        Args:
            output_dir: Directorio de salida
            headless: Si True, ejecuta el navegador sin interfaz gráfica
            usar_llm: Si True, procesa cada propiedad con el agente IA
        """
        self.output_dir = Path(output_dir)
        self.headless = headless
        self.usar_llm = usar_llm
        self.scraper = ParaisoDoradoScraper(output_dir=output_dir, headless=headless)
        
        # URL base del listado de propiedades
        # El scraper detectará automáticamente todas las páginas de paginación
        self.listado_urls = [
            "https://paraisodorado.com.mx/propiedades",  # URL principal (sin /es/)
            # No necesitas agregar ?page=2, ?page=3 manualmente
            # El método _buscar_paginas_adicionales() las detecta automáticamente
        ]
        
        # Estadísticas
        self.stats = {
            'total_encontradas': 0,
            'total_scrapeadas': 0,
            'exitosas': 0,
            'fallidas': 0,
            'errores': []
        }
    
    async def extraer_urls_propiedades(self) -> List[str]:
        """
        Extrae todas las URLs de propiedades del sitio
        
        Returns:
            list: Lista de URLs de propiedades
        """
        urls_propiedades = set()  # Usar set para evitar duplicados
        
        print("\n" + "="*80)
        print("🔍 EXTRAYENDO URLS DE PROPIEDADES")
        print("="*80 + "\n")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            page = await browser.new_page()
            
            try:
                # Navegar por cada página de listado
                for idx, listado_url in enumerate(self.listado_urls, 1):
                    print(f"📄 Página {idx}/{len(self.listado_urls)}: {listado_url}")
                    
                    try:
                        await page.goto(listado_url, wait_until='networkidle', timeout=60000)
                        await page.wait_for_timeout(3000)  # Esperar más tiempo
                        
                        # SCROLL para forzar carga de contenido lazy-loaded
                        print(f"   🔄 Haciendo scroll para cargar todo el contenido...")
                        await page.evaluate("""
                            async () => {
                                await new Promise((resolve) => {
                                    let totalHeight = 0;
                                    const distance = 100;
                                    const timer = setInterval(() => {
                                        const scrollHeight = document.body.scrollHeight;
                                        window.scrollBy(0, distance);
                                        totalHeight += distance;
                                        if(totalHeight >= scrollHeight){
                                            clearInterval(timer);
                                            resolve();
                                        }
                                    }, 100);
                                });
                            }
                        """)
                        
                        await page.wait_for_timeout(2000)  # Esperar después del scroll
                        
                        # Buscar enlaces con MÚLTIPLES selectores
                        selectores = [
                            'a[href*="/propiedad/"]',
                            'a[href*="propiedad"]',
                            '[href*="/propiedad/"]',
                            '.property-card a',
                            '[class*="property"] a',
                            '[class*="propiedad"] a',
                        ]
                        
                        enlaces_totales = set()
                        for selector in selectores:
                            try:
                                enlaces = await page.query_selector_all(selector)
                                for enlace in enlaces:
                                    href = await enlace.get_attribute('href')
                                    if href and '/propiedad/' in href:
                                        enlaces_totales.add(href)
                            except:
                                continue
                        
                        print(f"   ✓ Enlaces encontrados en esta página: {len(enlaces_totales)}")
                        
                        for href in enlaces_totales:
                            # Convertir a URL absoluta
                            if href.startswith('/'):
                                url_completa = f"https://paraisodorado.com.mx{href}"
                            elif href.startswith('http'):
                                url_completa = href
                            else:
                                url_completa = f"https://paraisodorado.com.mx/{href}"
                            
                            # Filtrar solo URLs válidas de propiedades
                            if '/propiedad/' in url_completa and 'paraisodorado.com.mx' in url_completa:
                                urls_propiedades.add(url_completa)
                        
                        print(f"   ✓ URLs únicas acumuladas: {len(urls_propiedades)}")
                    
                    except Exception as e:
                        print(f"   ⚠ Error en página {idx}: {str(e)}")
                        continue
                
                # También intentar con búsqueda de paginación automática
                print(f"\n🔄 Buscando páginas adicionales automáticamente...")
                await self._buscar_paginas_adicionales(page, urls_propiedades)
                
            finally:
                await browser.close()
        
        urls_lista = sorted(list(urls_propiedades))
        self.stats['total_encontradas'] = len(urls_lista)
        
        print(f"\n✅ Total de propiedades encontradas: {len(urls_lista)}")
        
        return urls_lista
    
    async def _buscar_paginas_adicionales(self, page, urls_set: set):
        """
        Navega por todas las páginas haciendo CLICK en los botones de paginación
        
        Args:
            page: Página de Playwright
            urls_set: Set para agregar URLs encontradas
        """
        try:
            # Navegar a la primera página
            base_url = "https://paraisodorado.com.mx/es/propiedades"
            print(f"\n   🔄 Navegando a página principal: {base_url}")
            await page.goto(base_url, wait_until='networkidle', timeout=60000)
            await page.wait_for_timeout(2000)
            
            # Detectar cuántas páginas hay
            import re
            contenido = await page.content()
            match_total = re.search(r'(\d+)\s*Propiedades?\s+en\s+la\s+lista', contenido, re.IGNORECASE)
            if match_total:
                total_propiedades = int(match_total.group(1))
                print(f"   📊 Total de propiedades reportadas: {total_propiedades}")
            
            # Detectar botones de paginación
            try:
                # Buscar todos los botones de página
                botones_pagina = await page.query_selector_all('nav[aria-label*="pagination"] button')
                num_paginas = 0
                
                for boton in botones_pagina:
                    texto = await boton.inner_text()
                    if texto.strip().isdigit():
                        num_paginas = max(num_paginas, int(texto.strip()))
                
                print(f"   📄 Número de páginas detectadas: {num_paginas}")
            except Exception as e:
                print(f"   ⚠️  No se pudo detectar número de páginas: {e}")
                num_paginas = 12  # Fallback basado en lo que vimos
            
            # Navegar por TODAS las páginas haciendo CLICK
            print(f"\n   🔄 Estrategia: HACER CLICK en botones de paginación")
            
            for num_pagina in range(1, num_paginas + 1):
                try:
                    print(f"\n   📄 Página {num_pagina}/{num_paginas}")
                    
                    # Si no es la página 1, hacer click en el botón
                    if num_pagina > 1:
                        # Buscar el botón específico de esta página
                        try:
                            # Intentar varios selectores para el botón
                            selector_boton = f'nav[aria-label*="pagination"] button:has-text("{num_pagina}")'
                            boton = await page.query_selector(selector_boton)
                            
                            if not boton:
                                # Intentar selector alternativo
                                selector_boton = f'button[aria-label*="page {num_pagina}"]'
                                boton = await page.query_selector(selector_boton)
                            
                            if boton:
                                await boton.click()
                                print(f"      ✓ Click en botón página {num_pagina}")
                                await page.wait_for_timeout(2000)
                            else:
                                print(f"      ⚠️  No se encontró botón para página {num_pagina}")
                                continue
                        except Exception as e:
                            print(f"      ⚠️  Error haciendo click: {str(e)[:50]}")
                            continue
                    
                    # SCROLL COMPLETO para cargar todo el contenido
                    print(f"      🔄 Scrolling completo...")
                    await page.evaluate("""
                        async () => {
                            await new Promise((resolve) => {
                                let totalHeight = 0;
                                const distance = 100;
                                const timer = setInterval(() => {
                                    const scrollHeight = document.body.scrollHeight;
                                    window.scrollBy(0, distance);
                                    totalHeight += distance;
                                    if(totalHeight >= scrollHeight){
                                        clearInterval(timer);
                                        resolve();
                                    }
                                }, 50);
                            });
                        }
                    """)
                    
                    await page.wait_for_timeout(1500)
                    
                    # Extraer URLs de esta página
                    urls_antes = len(urls_set)
                    
                    selectores = [
                        'a[href*="/propiedad/"]',
                    ]
                    
                    for selector in selectores:
                        try:
                            enlaces = await page.query_selector_all(selector)
                            for enlace in enlaces:
                                href = await enlace.get_attribute('href')
                                if href and '/propiedad/' in href:
                                    if href.startswith('/'):
                                        url_completa = f"https://paraisodorado.com.mx{href}"
                                    elif href.startswith('http'):
                                        url_completa = href
                                    else:
                                        url_completa = f"https://paraisodorado.com.mx/{href}"
                                    
                                    if '/propiedad/' in url_completa:
                                        urls_set.add(url_completa)
                        except:
                            continue
                    
                    urls_despues = len(urls_set)
                    nuevas_urls = urls_despues - urls_antes
                    
                    print(f"      ✅ Encontradas {nuevas_urls} propiedades nuevas (total acumulado: {urls_despues})")
                
                except Exception as e:
                    print(f"      ⚠️  Error en página {num_pagina}: {str(e)[:50]}")
                    continue
        
        except Exception as e:
            print(f"   ⚠ Error navegando páginas: {str(e)}")
    
    async def scrapear_todas(self, urls: List[str], delay_entre_requests: float = 2.0):
        """
        Scrapeaq todas las propiedades
        
        Args:
            urls: Lista de URLs a scrapear
            delay_entre_requests: Delay en segundos entre requests (para ser respetuoso)
        """
        print("\n" + "="*80)
        print("🚀 INICIANDO SCRAPING MASIVO")
        print("="*80 + "\n")
        
        print(f"📊 Total de propiedades a scrapear: {len(urls)}")
        print(f"⏱️  Delay entre requests: {delay_entre_requests}s")
        print(f"📁 Directorio de salida: {self.output_dir}")
        print()
        
        inicio = datetime.now()
        
        for idx, url in enumerate(urls, 1):
            self.stats['total_scrapeadas'] += 1
            
            print(f"\n{'='*80}")
            print(f"🏠 Propiedad {idx}/{len(urls)} ({(idx/len(urls)*100):.1f}%)")
            print(f"{'='*80}")
            print(f"🔗 URL: {url}\n")
            
            try:
                # Scrapear la propiedad
                resultado = await self.scraper.extraer_informacion(url)

                # Procesar con agente IA si está habilitado
                if self.usar_llm and resultado.get('descripcion'):
                    try:
                        resultado = procesar_propiedad_con_llm(resultado)
                    except Exception as llm_error:
                        print(f"   ⚠️ Error en LLM (se conservan datos del scraper): {llm_error}")

                # Guardar JSON actualizado con datos del LLM
                if resultado.get('procesado_con_llm'):
                    json_path = self.output_dir / "json" / f"paraiso_dorado_{resultado.get('property_id', idx)}_llm.json"
                    json_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(resultado, f, indent=2, ensure_ascii=False)
                    print(f"   📄 JSON con análisis IA guardado: {json_path}")

                # Mostrar resumen rápido
                print(f"\n📋 Resumen:")
                print(f"   • Título: {resultado.get('titulo', 'N/A')[:60]}...")
                print(f"   • Precio: {resultado.get('precio', 'N/A')}")
                print(f"   • Tipo: {resultado.get('tipo_propiedad', 'N/A')}")
                print(f"   • Imágenes: {len(resultado.get('imagenes_descargadas', []))}")

                # Mostrar análisis IA si existe
                analisis = resultado.get('analisis_llm', {})
                if analisis and not analisis.get('error'):
                    print(f"   • 🤖 Análisis IA:")
                    if analisis.get('descripcion_comercial'):
                        print(f"     📝 {analisis['descripcion_comercial'][:120]}...")
                    if analisis.get('destacados_venta'):
                        for dest in analisis['destacados_venta'][:3]:
                            print(f"     ⭐ {dest}")

                self.stats['exitosas'] += 1
                print(f"\n✅ Propiedad {idx} scrapeada exitosamente!")
                
            except Exception as e:
                self.stats['fallidas'] += 1
                error_msg = f"Propiedad {idx} ({url}): {str(e)}"
                self.stats['errores'].append(error_msg)
                print(f"\n❌ Error en propiedad {idx}: {str(e)}")
            
            # Delay entre requests
            if idx < len(urls):  # No esperar después de la última
                print(f"\n⏳ Esperando {delay_entre_requests}s antes de la siguiente...")
                await asyncio.sleep(delay_entre_requests)
        
        # Calcular duración
        fin = datetime.now()
        duracion = fin - inicio
        
        # Mostrar estadísticas finales
        self._mostrar_estadisticas(duracion)
    
    def _mostrar_estadisticas(self, duracion):
        """Muestra estadísticas finales del scraping"""
        print("\n" + "="*80)
        print("📊 ESTADÍSTICAS FINALES")
        print("="*80 + "\n")
        
        print(f"🔍 Propiedades encontradas: {self.stats['total_encontradas']}")
        print(f"🚀 Propiedades scrapeadas: {self.stats['total_scrapeadas']}")
        print(f"✅ Exitosas: {self.stats['exitosas']}")
        print(f"❌ Fallidas: {self.stats['fallidas']}")
        print(f"⏱️  Duración total: {duracion}")
        print(f"📁 Archivos guardados en: {self.output_dir}/json/")
        print(f"🖼️  Imágenes guardadas en: {self.output_dir}/imagenes/")
        
        if self.stats['fallidas'] > 0:
            print(f"\n⚠️  ERRORES ({len(self.stats['errores'])}):")
            for error in self.stats['errores']:
                print(f"   • {error}")
        
        # Tasa de éxito
        if self.stats['total_scrapeadas'] > 0:
            tasa_exito = (self.stats['exitosas'] / self.stats['total_scrapeadas']) * 100
            print(f"\n📈 Tasa de éxito: {tasa_exito:.1f}%")
        
        print("\n" + "="*80)
        print("🏁 SCRAPING MASIVO COMPLETADO")
        print("="*80 + "\n")
    
    async def ejecutar(self, delay_entre_requests: float = 2.0):
        """
        Ejecuta el proceso completo de scraping masivo
        
        Args:
            delay_entre_requests: Delay en segundos entre requests
        """
        try:
            # Paso 1: Extraer URLs
            urls = await self.extraer_urls_propiedades()
            
            if not urls:
                print("❌ No se encontraron propiedades para scrapear")
                return
            
            # Paso 2: Confirmar con usuario (opcional)
            print(f"\n⚠️  Se encontraron {len(urls)} propiedades")
            print(f"⏱️  Tiempo estimado: ~{len(urls) * delay_entre_requests / 60:.1f} minutos")
            
            # Paso 3: Scrapear todas
            await self.scrapear_todas(urls, delay_entre_requests)
            
        except Exception as e:
            print(f"\n❌ Error fatal: {str(e)}")
            import traceback
            traceback.print_exc()


async def main():
    """Función principal"""
    print("\n" + "="*80)
    print("🏢 SCRAPER MASIVO DE PARAÍSO DORADO")
    print("="*80 + "\n")
    
    # Configuración
    OUTPUT_DIR = "data"
    HEADLESS = True  # Cambiar a False para ver el navegador
    DELAY_ENTRE_REQUESTS = 2.0  # segundos
    USAR_LLM = True  # Procesar cada propiedad con agente IA

    # Crear scraper masivo
    bulk_scraper = ParaisoDoradoBulkScraper(
        output_dir=OUTPUT_DIR,
        headless=HEADLESS,
        usar_llm=USAR_LLM
    )
    
    # Ejecutar
    await bulk_scraper.ejecutar(delay_entre_requests=DELAY_ENTRE_REQUESTS)


if __name__ == "__main__":
    asyncio.run(main())