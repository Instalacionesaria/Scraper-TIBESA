"""
Clase Base para todos los Scrapers
Proporciona funcionalidad común y estructura para scrapers específicos
"""

import asyncio
import json
import os
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright, Page
from typing import Optional, Dict, Any


class BaseScraper(ABC):
    """
    Clase base abstracta para todos los scrapers de propiedades.
    Define la estructura y funcionalidad común que todos los scrapers deben implementar.
    """
    
    def __init__(self, output_dir: str = "data", headless: bool = True):
        """
        Inicializa el scraper base
        
        Args:
            output_dir: Directorio donde se guardarán los datos e imágenes
            headless: Si es False, muestra el navegador (útil para debugging)
        """
        self.output_dir = Path(output_dir)
        self.images_dir = self.output_dir / "imagenes"
        self.json_dir = self.output_dir / "json"
        self.headless = headless
        
        # Crear directorios si no existen
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.json_dir.mkdir(parents=True, exist_ok=True)
        
        # Nombre del sitio (debe ser definido por cada scraper específico)
        self.site_name = "generic"
    
    @abstractmethod
    def get_selectors(self) -> Dict[str, Any]:
        """
        Retorna los selectores CSS/XPath específicos del sitio.
        Cada scraper debe implementar este método con sus propios selectores.
        
        Returns:
            dict: Diccionario con selectores organizados por tipo de dato
        """
        pass
    
    @abstractmethod
    async def extract_custom_data(self, page: Page, data: Dict) -> Dict:
        """
        Extrae datos específicos del sitio que no son comunes.
        Permite a cada scraper personalizar la extracción de datos únicos.
        
        Args:
            page: Página de Playwright
            data: Diccionario con datos ya extraídos
            
        Returns:
            dict: Diccionario actualizado con datos adicionales
        """
        pass
    
    def get_browser_config(self) -> Dict[str, Any]:
        """
        Retorna la configuración del navegador.
        Puede ser sobrescrita por scrapers específicos si necesitan configuración especial.
        
        Returns:
            dict: Configuración del navegador
        """
        return {
            'headless': self.headless,
            'args': [
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox'
            ]
        }
    
    def get_context_config(self) -> Dict[str, Any]:
        """
        Retorna la configuración del contexto del navegador.
        Puede ser sobrescrita por scrapers específicos.
        
        Returns:
            dict: Configuración del contexto
        """
        return {
            'viewport': {'width': 1920, 'height': 1080},
            'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'locale': 'es-MX',
            'timezone_id': 'America/Mexico_City'
        }
    
    async def wait_for_page_load(self, page: Page):
        """
        Espera a que la página cargue completamente.
        Puede ser sobrescrito por scrapers que necesiten lógica especial de espera.
        
        Args:
            page: Página de Playwright
        """
        await page.wait_for_selector('body', timeout=10000)
        await asyncio.sleep(2)  # Dar tiempo para contenido dinámico
    
    async def extraer_texto(self, page: Page, selectores: list, default: str = None) -> Optional[str]:
        """
        Intenta extraer texto usando múltiples selectores.
        
        Args:
            page: Página de Playwright
            selectores: Lista de selectores a probar
            default: Valor por defecto si no se encuentra nada
            
        Returns:
            str: Texto extraído o None
        """
        for selector in selectores:
            try:
                elemento = await page.query_selector(selector)
                if elemento:
                    texto = await elemento.text_content()
                    if texto and texto.strip():
                        return texto.strip()
            except:
                continue
        return default
    
    async def extraer_informacion(self, url: str) -> Dict[str, Any]:
        """
        Método principal que coordina todo el proceso de scraping.
        Este método usa los selectores y métodos específicos de cada scraper.
        
        Args:
            url: URL de la propiedad a scrapear
            
        Returns:
            dict: Diccionario con toda la información extraída
        """
        print(f"\n{'='*80}")
        print(f"🏠 SCRAPEANDO [{self.site_name.upper()}]: {url}")
        print(f"{'='*80}\n")
        
        async with async_playwright() as p:
            # Lanzar navegador con configuración
            browser_config = self.get_browser_config()
            browser = await p.chromium.launch(**browser_config)
            
            context_config = self.get_context_config()
            context = await browser.new_context(**context_config)
            
            # Ocultar que es automatización
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            page = await context.new_page()
            
            try:
                # Navegar a la página
                print("⏳ Cargando página...")
                await page.goto(url, wait_until='networkidle', timeout=60000)
                print("✓ Página cargada\n")
                
                # Esperar a que cargue
                await self.wait_for_page_load(page)
                
                # Estructura de datos base
                data = {
                    'url': url,
                    'site': self.site_name,
                    'fecha_scraping': datetime.now().isoformat(),
                    'empresa': None,
                    'titulo': None,
                    'ubicacion': None,
                    'precio': None,
                    'moneda': None,
                    'estado': None,
                    'tipo_propiedad': None,
                    'terreno': {},
                    'caracteristicas': {},
                    'descripcion': None,
                    'agente': {},
                    'imagenes': [],
                    'imagenes_descargadas': []
                }
                
                # Obtener selectores específicos del sitio
                selectores = self.get_selectors()
                
                # Extraer información común
                print("📊 Extrayendo información general...")
                
                # Título
                if 'titulo' in selectores:
                    data['titulo'] = await self.extraer_texto(page, selectores['titulo'])
                    print(f"   Título: {data['titulo']}")
                
                # Ubicación
                if 'ubicacion' in selectores:
                    data['ubicacion'] = await self.extraer_texto(page, selectores['ubicacion'])
                    print(f"   Ubicación: {data['ubicacion']}")
                
                # Precio
                if 'precio' in selectores:
                    precio_texto = await self.extraer_texto(page, selectores['precio'])
                    if precio_texto:
                        data['precio'] = precio_texto
                        # Extraer moneda
                        if 'MXN' in precio_texto or 'pesos' in precio_texto.lower():
                            data['moneda'] = 'MXN'
                        elif 'USD' in precio_texto or 'dólares' in precio_texto.lower():
                            data['moneda'] = 'USD'
                    print(f"   Precio: {data['precio']}")
                
                # Estado
                if 'estado' in selectores:
                    data['estado'] = await self.extraer_texto(page, selectores['estado'])
                    print(f"   Estado: {data['estado']}")
                
                # Descripción
                if 'descripcion' in selectores:
                    data['descripcion'] = await self.extraer_texto(page, selectores['descripcion'])
                    if data['descripcion']:
                        preview = data['descripcion'][:100] + '...' if len(data['descripcion']) > 100 else data['descripcion']
                        print(f"   Descripción: {preview}")
                
                print()
                
                # Extraer datos específicos del sitio
                print("🔍 Extrayendo datos específicos del sitio...")
                data = await self.extract_custom_data(page, data)
                print()
                
                # Guardar datos
                await self.guardar_datos(data)
                
                return data
                
            except Exception as e:
                print(f"\n❌ Error durante el scraping: {str(e)}")
                import traceback
                traceback.print_exc()
                raise
            
            finally:
                await browser.close()
    
    async def guardar_datos(self, data: Dict[str, Any]):
        """
        Guarda los datos extraídos en formato JSON.
        
        Args:
            data: Diccionario con los datos a guardar
        """
        # Guardar JSON
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        json_filename = f"{self.site_name}_{timestamp}.json"
        json_path = self.json_dir / json_filename
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'='*80}")
        print("✅ SCRAPING COMPLETADO")
        print(f"{'='*80}\n")
        print(f"📁 Datos guardados en: {json_path}")
        if data.get('imagenes_descargadas'):
            print(f"🖼️  Imágenes guardadas: {len(data['imagenes_descargadas'])}")
