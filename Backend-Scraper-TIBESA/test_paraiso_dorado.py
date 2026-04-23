"""
Script de prueba para el Scraper de Paraíso Dorado
Prueba el nuevo sistema modular de scrapers
"""

import asyncio
import sys
from pathlib import Path

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent))

from scrapers.paraiso_dorado import ParaisoDoradoScraper


async def test_paraiso_dorado():
    """Prueba el scraper de Paraíso Dorado"""
    
    print("\n" + "="*80)
    print("🧪 PRUEBA DEL SCRAPER DE PARAÍSO DORADO")
    print("="*80 + "\n")
    
    # URLs de prueba
    test_urls = [
        "https://paraisodorado.com.mx/es/propiedad/departamento-en-brisas-del-vigia-id275",
        # Puedes agregar más URLs aquí
    ]
    
    # Crear scraper
    scraper = ParaisoDoradoScraper(output_dir="data", headless=True)
    
    for idx, url in enumerate(test_urls, 1):
        print(f"\n{'='*80}")
        print(f"Prueba {idx}/{len(test_urls)}")
        print(f"{'='*80}\n")
        
        try:
            # Scrapear
            resultado = await scraper.extraer_informacion(url)
            
            # Mostrar resumen
            print(f"\n{'='*80}")
            print("📊 RESUMEN DE DATOS EXTRAÍDOS")
            print(f"{'='*80}\n")
            
            print(f"🏢 Empresa: {resultado.get('empresa')}")
            print(f"📝 Título: {resultado.get('titulo')}")
            print(f"📍 Ubicación: {resultado.get('ubicacion')}")
            print(f"💰 Precio: {resultado.get('precio')}")
            print(f"🏷️  Estado: {resultado.get('estado')}")
            print(f"🏠 Tipo: {resultado.get('tipo_propiedad', 'N/A').replace('_', ' ').title()}")
            
            if resultado.get('terreno'):
                print(f"\n📐 Terreno:")
                for key, value in resultado['terreno'].items():
                    emoji = "📏" if key == "superficie" else "↔️" if key == "frente" else "↕️" if key == "fondo" else "💧" if key == "laguna" else "🛣️"
                    print(f"   {emoji} {key}: {value}")
            
            if resultado.get('caracteristicas'):
                print(f"\n✨ Características:")
                for key, value in resultado['caracteristicas'].items():
                    emoji = "🌾" if key == "agricola" else "🌽" if key == "cultivos" else "💧" if key == "riego" else "🏊" if key == "laguna" else "📍"
                    if isinstance(value, bool):
                        print(f"   {emoji} {key}: {'Sí' if value else 'No'}")
                    else:
                        print(f"   {emoji} {key}: {value}")
            
            if resultado.get('agente'):
                print(f"\n👤 Agente:")
                for key, value in resultado['agente'].items():
                    print(f"   • {key}: {value}")
            
            print(f"\n🖼️  Imágenes:")
            print(f"   • URLs encontradas: {len(resultado.get('imagenes', []))}")
            print(f"   • Descargadas: {len(resultado.get('imagenes_descargadas', []))}")
            
            if resultado.get('descripcion'):
                desc = resultado['descripcion']
                preview = desc[:200] + "..." if len(desc) > 200 else desc
                print(f"\n📄 Descripción: {preview}")
            
            print(f"\n✅ Prueba {idx} completada exitosamente!")
            
        except Exception as e:
            print(f"\n❌ Error en prueba {idx}: {str(e)}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*80}")
    print("🏁 TODAS LAS PRUEBAS COMPLETADAS")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    # Ejecutar pruebas
    asyncio.run(test_paraiso_dorado())
