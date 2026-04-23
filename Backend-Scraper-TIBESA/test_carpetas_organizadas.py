"""
Script de prueba rápido para verificar la organización de imágenes por carpetas
Scrapeaq 2-3 propiedades para demostrar la nueva estructura
"""

import asyncio
import sys
from pathlib import Path

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent))

from scrapers.paraiso_dorado import ParaisoDoradoScraper


async def test_organizacion_carpetas():
    """Prueba la organización de imágenes por carpetas"""
    print("\n" + "="*80)
    print("🧪 TEST DE ORGANIZACIÓN POR CARPETAS")
    print("="*80 + "\n")
    
    print("ℹ️  Este script scrapeaq 2-3 propiedades para demostrar")
    print("ℹ️  la nueva organización de imágenes por carpetas\n")
    
    # URLs de prueba (2-3 propiedades)
    urls_prueba = [
        "https://paraisodorado.com.mx/es/propiedad/departamento-en-brisas-del-vigia-id275",
        "https://paraisodorado.com.mx/es/propiedad/oportunidad-de-excelente-inversion-en-el-walamo-id153",
    ]
    
    # Crear scraper
    scraper = ParaisoDoradoScraper(output_dir="data", headless=True)
    
    print(f"📊 Propiedades a scrapear: {len(urls_prueba)}\n")
    
    for idx, url in enumerate(urls_prueba, 1):
        print(f"{'='*80}")
        print(f"🏠 Propiedad {idx}/{len(urls_prueba)}")
        print(f"{'='*80}")
        print(f"🔗 {url}\n")
        
        try:
            resultado = await scraper.extraer_informacion(url)
            
            print(f"\n✅ Scraping completado!")
            print(f"   • Título: {resultado.get('titulo', 'N/A')[:50]}...")
            print(f"   • ID: {resultado.get('property_id', 'N/A')}")
            print(f"   • Imágenes descargadas: {len(resultado.get('imagenes_descargadas', []))}")
            
            if resultado.get('imagenes_descargadas'):
                primera_imagen = resultado['imagenes_descargadas'][0]
                print(f"   • Primera imagen: {primera_imagen}")
            
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")
        
        if idx < len(urls_prueba):
            print(f"\n⏳ Esperando 2s...\n")
            await asyncio.sleep(2)
    
    # Mostrar estructura de carpetas
    print("\n" + "="*80)
    print("📂 ESTRUCTURA DE CARPETAS RESULTANTE")
    print("="*80 + "\n")
    
    imagenes_dir = Path("data/imagenes")
    
    if imagenes_dir.exists():
        carpetas = sorted([d for d in imagenes_dir.iterdir() if d.is_dir()])
        
        if carpetas:
            print("data/imagenes/")
            for carpeta in carpetas:
                imagenes = list(carpeta.glob("*"))
                print(f"├── {carpeta.name}/  ({len(imagenes)} imágenes)")
                
                # Mostrar primeras 3 imágenes de ejemplo
                for i, img in enumerate(sorted(imagenes)[:3]):
                    prefijo = "│   ├──" if i < min(2, len(imagenes)-1) else "│   └──"
                    print(f"{prefijo} {img.name}")
                
                if len(imagenes) > 3:
                    print(f"│       ... y {len(imagenes) - 3} más")
            
            print(f"\n✅ Total de carpetas creadas: {len(carpetas)}")
            print(f"📊 Cada carpeta contiene las imágenes de una propiedad específica")
        else:
            print("⚠️  No se encontraron carpetas (puede que hayan fallado las descargas)")
    else:
        print("⚠️  El directorio de imágenes no existe aún")
    
    print("\n" + "="*80)
    print("🎯 VENTAJAS DE LA NUEVA ORGANIZACIÓN")
    print("="*80 + "\n")
    
    print("✅ Imágenes organizadas por propiedad")
    print("✅ Fácil identificar qué imágenes pertenecen a cada inmueble")
    print("✅ Nombres de archivo más simples (imagen_1, imagen_2, etc.)")
    print("✅ Carpetas con ID de propiedad (propiedad_275, propiedad_153, etc.)")
    print("✅ Facilita la gestión y respaldo de imágenes específicas")
    
    print("\n" + "="*80)
    print("✅ TEST COMPLETADO")
    print("="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(test_organizacion_carpetas())


