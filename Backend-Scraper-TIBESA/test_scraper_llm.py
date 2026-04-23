"""
Script de prueba: Scraper + LLM
Prueba el sistema completo con procesamiento de OpenAI
"""

import asyncio
import sys
import json
from pathlib import Path

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent))

from scrapers.paraiso_dorado import ParaisoDoradoScraper
from utils.agente_propiedades import procesar_propiedad_con_llm


async def test_scraper_con_llm():
    """Prueba el scraper de Paraíso Dorado con procesamiento LLM"""
    
    print("\n" + "="*80)
    print("🧪 PRUEBA: SCRAPER + LLM (OpenAI)")
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
            # PASO 1: Scrapear con Playwright
            print("📥 PASO 1: Scrapeando con Playwright...")
            resultado_scraper = await scraper.extraer_informacion(url)
            print("✅ Scraping completado\n")
            
            # PASO 2: Procesar con LLM
            print("🤖 PASO 2: Procesando descripción con OpenAI...")
            resultado_completo = procesar_propiedad_con_llm(resultado_scraper)
            print("✅ Procesamiento LLM completado\n")
            
            # Guardar JSON con datos del LLM
            timestamp = resultado_scraper.get('fecha_scraping', '').replace(':', '-').split('.')[0]
            json_filename = f"propiedad_llm_{timestamp}.json"
            json_path = Path("data/json") / json_filename
            
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(resultado_completo, f, indent=2, ensure_ascii=False)
            
            print(f"💾 Datos guardados en: {json_path}\n")
            
            # MOSTRAR COMPARACIÓN
            print(f"\n{'='*80}")
            print("📊 COMPARACIÓN: SCRAPER vs LLM")
            print(f"{'='*80}\n")
            
            # Datos del scraper
            print("🔧 DATOS DEL SCRAPER (Playwright):")
            print(f"   Título: {resultado_scraper.get('titulo')}")
            print(f"   Tipo (scraper): {resultado_scraper.get('tipo_propiedad')}")
            print(f"   Precio: {resultado_scraper.get('precio')}")
            print(f"   Ubicación: {resultado_scraper.get('ubicacion')}\n")
            
            # Datos del LLM
            datos_llm = resultado_completo.get('datos_llm', {})
            print("🤖 DATOS EXTRAÍDOS POR LLM (OpenAI):")
            print(f"   Tipo (LLM): {datos_llm.get('tipo_propiedad')}")
            
            if datos_llm.get('construccion'):
                print(f"   Construcción: {datos_llm['construccion']}")
            
            if datos_llm.get('terreno'):
                print(f"   Terreno: {datos_llm['terreno']}")
            
            if datos_llm.get('espacios'):
                print(f"   Espacios: {datos_llm['espacios']}")
            
            if datos_llm.get('amenidades'):
                print(f"\n   Amenidades detectadas por LLM:")
                for amenidad in datos_llm['amenidades']:
                    print(f"      • {amenidad}")
            
            if datos_llm.get('caracteristicas'):
                print(f"\n   Características:")
                for key, value in datos_llm['caracteristicas'].items():
                    print(f"      • {key}: {value}")
            
            if datos_llm.get('descripcion_limpia'):
                print(f"\n   Descripción limpia:")
                print(f"      {datos_llm['descripcion_limpia']}")
            
            # Metadata del LLM
            llm_metadata = datos_llm.get('_llm_metadata', {})
            if llm_metadata:
                print(f"\n   💰 Tokens usados: {llm_metadata.get('tokens_usados')}")
                print(f"   🤖 Modelo: {llm_metadata.get('model')}")
            
            print(f"\n✅ Prueba {idx} completada exitosamente!")
            
        except Exception as e:
            print(f"\n❌ Error en prueba {idx}: {str(e)}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*80}")
    print("🏁 TODAS LAS PRUEBAS COMPLETADAS")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    # Verificar que existe .env
    env_path = Path(".env")
    if not env_path.exists():
        print("\n⚠️  ADVERTENCIA: No se encontró archivo .env")
        print("\n📝 Pasos para configurar:")
        print("   1. Copia .env.example a .env:")
        print("      cp .env.example .env")
        print("   2. Edita .env y agrega tu OPENAI_API_KEY")
        print("   3. Ejecuta este script de nuevo\n")
        sys.exit(1)
    
    # Ejecutar pruebas
    asyncio.run(test_scraper_con_llm())
