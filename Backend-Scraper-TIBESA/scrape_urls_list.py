"""
Script para scrapear una lista específica de URLs de Paraíso Dorado
Útil cuando ya tienes las URLs de las propiedades que quieres scrapear
"""

import asyncio
import sys
from pathlib import Path
from typing import List
from datetime import datetime

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent))

from scrapers.paraiso_dorado import ParaisoDoradoScraper


async def scrapear_lista_urls(urls: List[str], output_dir: str = "data", 
                               headless: bool = True, delay: float = 2.0):
    """
    Scrapeaq una lista específica de URLs
    
    Args:
        urls: Lista de URLs a scrapear
        output_dir: Directorio de salida
        headless: Si True, ejecuta sin interfaz gráfica
        delay: Segundos entre cada request
    """
    print("\n" + "="*80)
    print("🚀 SCRAPING DE LISTA DE URLS")
    print("="*80 + "\n")
    
    print(f"📊 Total de URLs: {len(urls)}")
    print(f"⏱️  Delay entre requests: {delay}s")
    print(f"📁 Directorio de salida: {output_dir}\n")
    
    # Crear scraper
    scraper = ParaisoDoradoScraper(output_dir=output_dir, headless=headless)
    
    # Estadísticas
    exitosas = 0
    fallidas = 0
    errores = []
    
    inicio = datetime.now()
    
    # Scrapear cada URL
    for idx, url in enumerate(urls, 1):
        print(f"\n{'='*80}")
        print(f"🏠 Propiedad {idx}/{len(urls)} ({(idx/len(urls)*100):.1f}%)")
        print(f"{'='*80}")
        print(f"🔗 URL: {url}\n")
        
        try:
            # Scrapear
            resultado = await scraper.extraer_informacion(url)
            
            # Resumen
            print(f"\n📋 Resumen:")
            print(f"   • Título: {resultado.get('titulo', 'N/A')[:60]}...")
            print(f"   • Precio: {resultado.get('precio', 'N/A')}")
            print(f"   • Tipo: {resultado.get('tipo_propiedad', 'N/A')}")
            print(f"   • Imágenes: {len(resultado.get('imagenes_descargadas', []))}")
            
            exitosas += 1
            print(f"\n✅ Propiedad {idx} scrapeada exitosamente!")
            
        except Exception as e:
            fallidas += 1
            error_msg = f"URL {idx} ({url}): {str(e)}"
            errores.append(error_msg)
            print(f"\n❌ Error: {str(e)}")
        
        # Delay
        if idx < len(urls):
            print(f"\n⏳ Esperando {delay}s...")
            await asyncio.sleep(delay)
    
    # Estadísticas finales
    fin = datetime.now()
    duracion = fin - inicio
    
    print("\n" + "="*80)
    print("📊 ESTADÍSTICAS FINALES")
    print("="*80 + "\n")
    
    print(f"🚀 Total procesadas: {len(urls)}")
    print(f"✅ Exitosas: {exitosas}")
    print(f"❌ Fallidas: {fallidas}")
    print(f"⏱️  Duración: {duracion}")
    
    if errores:
        print(f"\n⚠️  ERRORES:")
        for error in errores:
            print(f"   • {error}")
    
    if len(urls) > 0:
        tasa = (exitosas / len(urls)) * 100
        print(f"\n📈 Tasa de éxito: {tasa:.1f}%")
    
    print("\n" + "="*80)
    print("🏁 SCRAPING COMPLETADO")
    print("="*80 + "\n")


async def main():
    """Función principal con URLs de ejemplo"""
    
    # 📝 CONFIGURA TUS URLs AQUÍ
    urls_a_scrapear = [
        "https://paraisodorado.com.mx/es/propiedad/departamento-en-brisas-del-vigia-id275",
        "https://paraisodorado.com.mx/es/propiedad/oportunidad-de-excelente-inversion-en-el-walamo-id153",
        # Agrega más URLs aquí...
    ]
    
    # ⚙️ CONFIGURACIÓN
    OUTPUT_DIR = "data"
    HEADLESS = True  # Cambiar a False para ver el navegador
    DELAY = 2.0  # Segundos entre requests
    
    # Ejecutar
    await scrapear_lista_urls(
        urls=urls_a_scrapear,
        output_dir=OUTPUT_DIR,
        headless=HEADLESS,
        delay=DELAY
    )


if __name__ == "__main__":
    # Ejemplo de uso desde línea de comandos:
    # python scrape_urls_list.py
    
    asyncio.run(main())

