"""
Script de prueba rápida del scraper
Ejecuta el scraper y muestra los resultados en consola
"""

import asyncio
from scraper_propiedades import PropiedadScraper


async def test_scraper():
    """Prueba el scraper con una propiedad de ejemplo"""
    
    print("\n" + "="*80)
    print("🏠 TEST DEL SCRAPER DE PROPIEDADES")
    print("="*80 + "\n")
    
    # URL de prueba
    url = "https://paraisodorado.com.mx/es/propiedad/porpiedad-en-playa-sur-id273"
    
    print(f"📍 URL a scrapear: {url}\n")
    
    # Crear scraper
    scraper = PropiedadScraper(output_dir="data")
    
    # Extraer información
    try:
        datos = await scraper.extraer_informacion(url)
        
        # Mostrar resumen
        print("\n" + "="*80)
        print("📊 RESUMEN DE EXTRACCIÓN")
        print("="*80 + "\n")
        
        print(f"🏢 Empresa: {datos.get('empresa', 'N/A')}")
        print(f"📝 Título: {datos.get('titulo', 'N/A')}")
        print(f"📍 Ubicación: {datos.get('ubicacion', 'N/A')}")
        print(f"💰 Precio: {datos.get('precio', 'N/A')}")
        print(f"🏷️  Estado: {datos.get('estado', 'N/A')}")
        
        if datos.get('terreno'):
            print(f"\n📐 TERRENO:")
            for key, value in datos['terreno'].items():
                print(f"   • {key.capitalize()}: {value}")
        
        if datos.get('agente'):
            print(f"\n👤 AGENTE:")
            for key, value in datos['agente'].items():
                if value:
                    print(f"   • {key.capitalize()}: {value}")
        
        print(f"\n🖼️  Imágenes encontradas: {len(datos.get('imagenes', []))}")
        print(f"💾 Imágenes descargadas: {len(datos.get('imagenes_descargadas', []))}")
        
        if datos.get('descripcion'):
            print(f"\n📄 DESCRIPCIÓN (primeros 200 caracteres):")
            desc_preview = datos['descripcion'][:200] + "..." if len(datos['descripcion']) > 200 else datos['descripcion']
            print(f"   {desc_preview}")
        
        print("\n" + "="*80)
        print("✅ TEST COMPLETADO EXITOSAMENTE")
        print("="*80 + "\n")
        
        print(f"📁 Archivos guardados en:")
        print(f"   • JSON: data/json/")
        print(f"   • Imágenes: data/imagenes/")
        
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
    else:
        print("\n⚠️  Hubo problemas. Revisa los errores arriba.")

