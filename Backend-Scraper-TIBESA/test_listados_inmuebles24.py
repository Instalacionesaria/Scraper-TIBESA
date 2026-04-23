"""
Script de prueba para el scraper de listados de Inmuebles24
"""

import asyncio
from scraper_listados_inmuebles24 import ListadosInmuebles24Scraper


async def test_scraper():
    """Prueba el scraper con una URL de ejemplo"""
    
    print("\n" + "="*80)
    print("📋 TEST SCRAPER DE LISTADOS - INMUEBLES24")
    print("="*80 + "\n")
    
    # URL del listado de inmuebles24
    url_listado = "https://www.inmuebles24.com/terrenos-en-venta-en-mazatlan.html"
    
    print(f"📍 URL a scrapear: {url_listado}\n")
    
    # Crear scraper
    # Cambiar headless=False para ver el navegador (debugging)
    scraper = ListadosInmuebles24Scraper(output_dir="data", headless=True)
    
    # Extraer URLs
    try:
        resultado = await scraper.extraer_urls_listado(url_listado)
        
        print("\n" + "="*80)
        print("📊 RESUMEN FINAL")
        print("="*80 + "\n")
        
        print(f"✅ Total esperado: {resultado.get('total_resultados_esperados', 'N/A')}")
        print(f"✅ URLs encontradas: {resultado.get('urls_encontradas', 0)}")
        print(f"✅ Archivo guardado: data/json/listado_inmuebles24_*.json")
        
        if resultado.get('urls'):
            print(f"\n🔗 Primeras 10 URLs extraídas:")
            for i, url in enumerate(resultado['urls'][:10], 1):
                print(f"   {i}. {url}")
            
            if len(resultado['urls']) > 10:
                print(f"\n   ... y {len(resultado['urls']) - 10} URLs más")
        
        print("\n" + "="*80)
        print("✅ TEST COMPLETADO EXITOSAMENTE")
        print("="*80 + "\n")
        
        return True
        
    except Exception as e:
        print("\n" + "="*80)
        print("❌ ERROR EN EL TEST")
        print("="*80 + "\n")
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    resultado = asyncio.run(test_scraper())
    
    if resultado:
        print("\n✨ Todo funcionó correctamente!")
        print("\n💡 Próximo paso: Usar estas URLs con el scraper de detalles")
    else:
        print("\n⚠️  Hubo problemas. Revisa los errores arriba.")

