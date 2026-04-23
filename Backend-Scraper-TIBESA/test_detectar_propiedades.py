"""
Script de prueba rápido para detectar cuántas propiedades hay en Paraíso Dorado
SIN hacer el scraping completo (solo detecta URLs)
"""

import asyncio
import sys
from pathlib import Path

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent))

from scrape_all_paraiso_dorado import ParaisoDoradoBulkScraper


async def test_deteccion():
    """Prueba rápida de detección de propiedades"""
    print("\n" + "="*80)
    print("🔍 TEST DE DETECCIÓN DE PROPIEDADES")
    print("="*80 + "\n")
    
    print("ℹ️  Este script solo detecta URLs, NO scrapeaq las propiedades")
    print("ℹ️  Es rápido y sirve para verificar cuántas propiedades hay\n")
    
    # Crear scraper
    scraper = ParaisoDoradoBulkScraper(output_dir="data", headless=True)
    
    # Solo extraer URLs (no scrapear)
    urls = await scraper.extraer_urls_propiedades()
    
    # Mostrar resultados
    print("\n" + "="*80)
    print("📊 RESULTADOS DE LA DETECCIÓN")
    print("="*80 + "\n")
    
    print(f"✅ Total de propiedades detectadas: {len(urls)}\n")
    
    if urls:
        print("📝 Primeras 10 URLs encontradas:")
        for idx, url in enumerate(urls[:10], 1):
            # Extraer ID de la URL
            import re
            match = re.search(r'id(\d+)', url)
            prop_id = match.group(1) if match else "?"
            
            # Extraer nombre corto de la URL
            nombre = url.split('/')[-1].replace('-', ' ').title()
            nombre_corto = nombre[:50] + "..." if len(nombre) > 50 else nombre
            
            print(f"   {idx:2d}. ID {prop_id:4s} - {nombre_corto}")
        
        if len(urls) > 10:
            print(f"   ... y {len(urls) - 10} más\n")
    
    # Estimación de tiempo
    DELAY_PROMEDIO = 2.0  # segundos
    TIEMPO_POR_PROPIEDAD = 10  # segundos (promedio)
    
    tiempo_estimado_segundos = len(urls) * (TIEMPO_POR_PROPIEDAD + DELAY_PROMEDIO)
    tiempo_estimado_minutos = tiempo_estimado_segundos / 60
    
    print("\n⏱️  ESTIMACIONES PARA SCRAPING COMPLETO:")
    print(f"   • Propiedades: {len(urls)}")
    print(f"   • Tiempo estimado: ~{tiempo_estimado_minutos:.1f} minutos")
    print(f"   • Delay entre requests: {DELAY_PROMEDIO}s")
    
    print("\n💡 SIGUIENTE PASO:")
    print("   Para scrapear todas las propiedades, ejecuta:")
    print("   → python scrape_all_paraiso_dorado.py")
    
    print("\n" + "="*80)
    print("✅ TEST COMPLETADO")
    print("="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(test_deteccion())


