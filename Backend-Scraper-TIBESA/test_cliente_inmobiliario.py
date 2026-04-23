"""
Script de prueba: Scraper + LLM - Output Limpio para Cliente Inmobiliario
Muestra solo datos relevantes para venta y análisis
"""

import asyncio
import sys
import json
from pathlib import Path

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent))

from scrapers.paraiso_dorado import ParaisoDoradoScraper
from utils.agente_propiedades import procesar_propiedad_con_llm


async def test_scraper_limpio():
    """Prueba el scraper con output limpio para cliente inmobiliario"""
    
    print("\n" + "="*80)
    print("🏠 EXTRACCIÓN DE DATOS DE PROPIEDADES")
    print("="*80 + "\n")
    
    # URLs de prueba
    test_urls = [
        "https://paraisodorado.com.mx/es/propiedad/departamento-en-brisas-del-vigia-id275",
    ]
    
    # Crear scraper (modo silencioso)
    scraper = ParaisoDoradoScraper(output_dir="data", headless=True)
    
    for idx, url in enumerate(test_urls, 1):
        print(f"Procesando propiedad {idx}/{len(test_urls)}...")
        print(f"URL: {url}\n")
        
        try:
            # PASO 1: Scrapear (sin prints)
            resultado_scraper = await scraper.extraer_informacion(url)
            
            # PASO 2: Procesar con LLM (sin prints)
            print("🤖 Analizando descripción con IA...")
            resultado_completo = procesar_propiedad_con_llm(resultado_scraper)
            datos_llm = resultado_completo.get('datos_llm', {})
            print("✅ Análisis completado\n")
            
            # ========================================
            # MOSTRAR SOLO DATOS PARA CLIENTE
            # ========================================
            
            print("="*80)
            print("📋 FICHA TÉCNICA DE LA PROPIEDAD")
            print("="*80 + "\n")
            
            # INFORMACIÓN BÁSICA
            print("📌 INFORMACIÓN GENERAL")
            print("-" * 40)
            print(f"Título: {resultado_scraper.get('titulo')}")
            print(f"Ubicación: {resultado_scraper.get('ubicacion')}")
            print(f"Precio: {resultado_scraper.get('precio')}")
            print(f"Estado: {resultado_scraper.get('estado')}")
            print(f"Tipo: {datos_llm.get('tipo_propiedad', 'N/A').upper()}")
            
            # CONSTRUCCIÓN
            construccion = datos_llm.get('construccion', {})
            if construccion.get('metros_cuadrados'):
                print(f"\n📐 CONSTRUCCIÓN")
                print("-" * 40)
                print(f"Superficie: {construccion.get('metros_cuadrados')} m²")
                if construccion.get('estado_construccion'):
                    print(f"Estado: {construccion.get('estado_construccion')}")
            
            # ESPACIOS
            espacios = datos_llm.get('espacios_interiores', {})
            if any(espacios.values()):
                print(f"\n🏠 ESPACIOS")
                print("-" * 40)
                if espacios.get('recamaras'):
                    print(f"Recámaras: {espacios.get('recamaras')}")
                if espacios.get('baños_completos'):
                    print(f"Baños completos: {espacios.get('baños_completos')}")
                if espacios.get('medios_baños'):
                    print(f"Medios baños: {espacios.get('medios_baños')}")
                if espacios.get('balcon'):
                    print(f"Balcón: Sí")
                if espacios.get('terraza'):
                    print(f"Terraza: Sí")
                if espacios.get('area_lavado'):
                    print(f"Área de lavado: Sí")
                if espacios.get('cocina_equipada'):
                    print(f"Cocina equipada: Sí")
            
            # ESTACIONAMIENTO
            estacionamiento = datos_llm.get('estacionamiento', {})
            if estacionamiento.get('tiene'):
                print(f"\n🚗 ESTACIONAMIENTO")
                print("-" * 40)
                print(f"Espacios: {estacionamiento.get('espacios', 0)}")
                if estacionamiento.get('tipo'):
                    print(f"Tipo: {estacionamiento.get('tipo')}")
            
            # AMENIDADES DEL EDIFICIO
            amenidades_edificio = datos_llm.get('amenidades_edificio', {})
            amenidades_lista = [k for k, v in amenidades_edificio.items() if v == True]
            if amenidades_lista:
                print(f"\n✨ AMENIDADES DEL EDIFICIO")
                print("-" * 40)
                amenidades_nombres = {
                    'alberca': 'Alberca',
                    'gimnasio': 'Gimnasio',
                    'roof_garden': 'Roof Garden',
                    'roof_top': 'Roof Top',
                    'elevador': 'Elevador',
                    'seguridad_24h': 'Seguridad 24h',
                    'acceso_controlado': 'Acceso controlado',
                    'salon_eventos': 'Salón de eventos',
                    'area_juegos_ninos': 'Área de juegos',
                    'pet_friendly': 'Pet Friendly'
                }
                for amenidad in amenidades_lista:
                    nombre = amenidades_nombres.get(amenidad, amenidad.replace('_', ' ').title())
                    print(f"• {nombre}")
            
            # ACABADOS
            acabados = datos_llm.get('acabados_y_extras', {})
            if acabados.get('amueblado'):
                print(f"\n🛋️  EXTRAS")
                print("-" * 40)
                print(f"Amueblado: Sí")
                if acabados.get('clima_aa'):
                    print(f"Aire acondicionado: Sí")
            
            # DESTACADOS PARA VENTA
            destacados = datos_llm.get('destacados_venta', [])
            if destacados:
                print(f"\n⭐ PUNTOS DESTACADOS")
                print("-" * 40)
                for punto in destacados:
                    print(f"• {punto}")
            
            # DESCRIPCIÓN COMERCIAL
            desc_comercial = datos_llm.get('descripcion_comercial')
            if desc_comercial:
                print(f"\n📝 DESCRIPCIÓN")
                print("-" * 40)
                print(desc_comercial)
            
            # ANÁLISIS DE MERCADO
            analisis = datos_llm.get('analisis_mercado', {})
            if analisis:
                print(f"\n📊 ANÁLISIS DE MERCADO")
                print("-" * 40)
                if analisis.get('segmento'):
                    print(f"Segmento: {analisis.get('segmento').title()}")
                if analisis.get('target'):
                    print(f"Target: {analisis.get('target')}")
                if analisis.get('plusvalia'):
                    print(f"Plusvalía: {analisis.get('plusvalia').title()}")
            
            # CONTACTO
            agente = resultado_scraper.get('agente', {})
            if agente:
                print(f"\n👤 CONTACTO")
                print("-" * 40)
                if agente.get('nombre'):
                    print(f"Agente: {agente.get('nombre')}")
                if agente.get('telefono'):
                    print(f"Teléfono: {agente.get('telefono')}")
            
            # IMÁGENES
            num_imagenes = len(resultado_scraper.get('imagenes', []))
            if num_imagenes > 0:
                print(f"\n🖼️  MULTIMEDIA")
                print("-" * 40)
                print(f"Fotografías: {num_imagenes} imágenes disponibles")
            
            print("\n" + "="*80)
            print(f"✅ Propiedad procesada exitosamente")
            print("="*80 + "\n")
            
            # Guardar JSON completo
            timestamp = resultado_scraper.get('fecha_scraping', '').replace(':', '-').split('.')[0]
            json_filename = f"propiedad_{timestamp}.json"
            json_path = Path("data/json") / json_filename
            
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(resultado_completo, f, indent=2, ensure_ascii=False)
            
            print(f"💾 Archivo completo guardado: {json_path}\n")
            
        except Exception as e:
            print(f"\n❌ Error procesando propiedad: {str(e)}\n")


if __name__ == "__main__":
    # Verificar que existe .env
    env_path = Path(".env")
    if not env_path.exists():
        print("\n⚠️  ADVERTENCIA: No se encontró archivo .env")
        print("Configura tu OPENAI_API_KEY en .env antes de continuar.\n")
        sys.exit(1)
    
    # Ejecutar
    asyncio.run(test_scraper_limpio())
