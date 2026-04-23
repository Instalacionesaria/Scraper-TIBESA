# 📋 Guía - Scraper de Listados Inmuebles24

Scraper para extraer todas las URLs de propiedades de una página de resultados de inmuebles24.

## 🎯 ¿Qué hace?

Extrae todas las URLs de propiedades individuales de una página de listados de inmuebles24.

**Ejemplo:**
- **Input:** `https://www.inmuebles24.com/terrenos-en-venta-en-mazatlan.html`
- **Output:** Lista de 262 URLs como:
  - `https://www.inmuebles24.com/inmueble/123456`
  - `https://www.inmuebles24.com/inmueble/789012`
  - etc.

## 🚀 Uso Rápido

### Opción 1: Script de Prueba (Recomendado)

```bash
# Activar entorno
conda activate ARIA-TIBESA-Scraper-2

# Ejecutar test
python test_listados_inmuebles24.py
```

### Opción 2: Uso Directo

```bash
python scraper_listados_inmuebles24.py
# Te pedirá la URL interactivamente
```

### Opción 3: Como Módulo

```python
import asyncio
from scraper_listados_inmuebles24 import ListadosInmuebles24Scraper

async def main():
    scraper = ListadosInmuebles24Scraper()
    resultado = await scraper.extraer_urls_listado(
        "https://www.inmuebles24.com/terrenos-en-venta-en-mazatlan.html"
    )
    
    print(f"Encontradas {resultado['urls_encontradas']} URLs")
    for url in resultado['urls'][:5]:
        print(f"  - {url}")

asyncio.run(main())
```

## 📊 Estructura del Output

El scraper guarda un archivo JSON en `data/json/listado_inmuebles24_TIMESTAMP.json`:

```json
{
  "url_listado": "https://www.inmuebles24.com/terrenos-en-venta-en-mazatlan.html",
  "fecha_scraping": "2025-11-25T16:30:00",
  "total_resultados_esperados": 262,
  "urls_encontradas": 262,
  "urls": [
    "https://www.inmuebles24.com/inmueble/123456",
    "https://www.inmuebles24.com/inmueble/789012",
    ...
  ]
}
```

## 🔍 Características

✅ **Extrae total de resultados** - Detecta "262 Terrenos en venta"  
✅ **Múltiples estrategias** - Usa varios selectores CSS para encontrar enlaces  
✅ **Sin duplicados** - Filtra URLs repetidas automáticamente  
✅ **Maneja paginación** - Si hay múltiples páginas, las scrapea todas  
✅ **Filtrado inteligente** - Solo incluye URLs de propiedades, no filtros/búsquedas  

## 📝 Ejemplo de Salida

```
================================================================================
📋 SCRAPEANDO LISTADO: https://www.inmuebles24.com/terrenos-en-venta-en-mazatlan.html
================================================================================

⏳ Cargando página de listados...
✓ Página cargada

📊 Extrayendo información del listado...
   ✓ Total de propiedades encontradas: 262

🔗 Extrayendo URLs de propiedades...
   🔍 Probando selector 'a[href*="/inmueble/"]': 262 enlaces encontrados
   ✓ URLs únicas encontradas: 262

📄 Verificando paginación...

================================================================================
✅ EXTRACCIÓN COMPLETADA
================================================================================

📊 RESUMEN:
   • Total esperado: 262
   • URLs encontradas: 262
   • Archivo guardado: data/json/listado_inmuebles24_20251125_163000.json

🔗 Primeras 5 URLs:
   1. https://www.inmuebles24.com/inmueble/123456
   2. https://www.inmuebles24.com/inmueble/789012
   3. https://www.inmuebles24.com/inmueble/345678
   4. https://www.inmuebles24.com/inmueble/901234
   5. https://www.inmuebles24.com/inmueble/567890
```

## 🔄 Próximo Paso

Una vez que tengas las URLs, puedes usarlas con el **scraper de detalles** para obtener información completa de cada propiedad.

```python
# Cargar URLs del listado
with open('data/json/listado_inmuebles24_*.json', 'r') as f:
    listado = json.load(f)

# Scrapear cada propiedad
for url in listado['urls']:
    # Usar scraper_propiedades.py aquí
    pass
```

## ⚙️ Configuración

### Cambiar directorio de salida

```python
scraper = ListadosInmuebles24Scraper(output_dir="mis_datos")
```

### Modo con interfaz gráfica (debug)

En `scraper_listados_inmuebles24.py`, línea 45:

```python
browser = await p.chromium.launch(headless=False)  # Ver navegador
```

## 🐛 Troubleshooting

### No encuentra URLs

1. Verifica que la URL sea correcta
2. Prueba con `headless=False` para ver qué pasa
3. Aumenta el tiempo de espera (línea 52): `await asyncio.sleep(5)`

### Encuentra menos URLs de las esperadas

1. Puede haber paginación - el scraper la maneja automáticamente
2. Algunas propiedades pueden estar en iframes
3. El contenido puede cargarse dinámicamente - aumenta el sleep

### Timeout errors

Aumenta timeout en línea 48:
```python
await page.goto(url_listado, wait_until='networkidle', timeout=120000)
```

## 📌 Notas

- El scraper espera 3 segundos después de cargar la página para contenido dinámico
- Si hay paginación, scrapea hasta 5 páginas adicionales (puedes aumentar este límite)
- Las URLs se guardan sin duplicados automáticamente

---

¡Listo para extraer listados! 🚀

