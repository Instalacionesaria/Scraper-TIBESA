# Scraper de Propiedades Inmobiliarias

Scraper profesional con Playwright para extraer información de propiedades en venta de sitios web inmobiliarios.

## 🎯 Datos que Extrae

- ✅ **Nombre de la empresa** inmobiliaria
- ✅ **Ubicación** de la propiedad (ciudad, estado)
- ✅ **Precio** (en pesos mexicanos o dólares)
- ✅ **Datos del terreno** (superficie, frente, fondo)
- ✅ **Descripción** completa de la propiedad
- ✅ **Información del agente** (nombre, cargo, teléfono)
- ✅ **Imágenes** (descargadas localmente)

## 📦 Instalación

### Opción A: Instalación Automática (Recomendado)

```bash
# Ejecutar script de instalación
chmod +x setup.sh
./setup.sh
```

El script creará automáticamente un entorno conda llamado `ARIA-TIBESA-Scraper-2` con Python 3.11.

### Opción B: Instalación Manual con Conda

```bash
# 1. Crear entorno conda con Python 3.11
conda create -n ARIA-TIBESA-Scraper-2 python=3.11 -y

# 2. Activar entorno
conda activate ARIA-TIBESA-Scraper-2

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Instalar navegadores de Playwright
playwright install chromium
```

### Opción C: Instalación con venv (alternativa)

```bash
# 1. Crear entorno virtual
python -m venv venv
source venv/bin/activate  # En Mac/Linux

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Instalar navegadores
playwright install chromium
```

## 🚀 Uso

### Opción 1: Ejecutar directamente

```bash
python scraper_propiedades.py
```

### Opción 2: Usar como módulo

```python
import asyncio
from scraper_propiedades import PropiedadScraper

async def main():
    # Crear scraper
    scraper = PropiedadScraper(output_dir="mis_datos")
    
    # URL de la propiedad
    url = "https://paraisodorado.com.mx/es/propiedad/porpiedad-en-playa-sur-id273"
    
    # Extraer datos
    datos = await scraper.extraer_informacion(url)
    
    print(f"Título: {datos['titulo']}")
    print(f"Precio: {datos['precio']}")

asyncio.run(main())
```

## 📁 Estructura de Salida

```
data/
├── json/
│   └── propiedad_20251125_143022.json
└── imagenes/
    ├── propiedad_20251125_143022_1.jpg
    ├── propiedad_20251125_143022_2.jpg
    └── ...
```

## 📄 Formato JSON

```json
{
  "url": "https://...",
  "fecha_scraping": "2025-11-25T14:30:22",
  "empresa": "Paraíso Dorado",
  "titulo": "PORPIEDAD EN PLAYA SUR",
  "ubicacion": "PLAYA SUR, Mazatlán, Sinaloa",
  "precio": "$3,700,000 MXN",
  "moneda": "MXN",
  "estado": "EN VENTA",
  "terreno": {
    "superficie": "180 m²",
    "frente": "15 metros",
    "fondo": "12 metros"
  },
  "descripcion": "La propiedad ideal para...",
  "agente": {
    "nombre": "Sergio Girón",
    "cargo": "Director",
    "telefono": "(669) 994-7029"
  },
  "imagenes": ["https://...", "https://..."],
  "imagenes_descargadas": ["data/imagenes/propiedad_..._1.jpg", ...]
}
```

## 🔧 Características Técnicas

- **Asíncrono**: Descarga múltiples imágenes en paralelo
- **Robusto**: Manejo de errores y timeouts
- **Flexible**: Usa múltiples selectores para encontrar datos
- **Headless**: Ejecuta el navegador en segundo plano
- **User Agent Real**: Evita bloqueos básicos

## 🎨 Personalización

### Cambiar directorio de salida

```python
scraper = PropiedadScraper(output_dir="mi_carpeta")
```

### Modo con interfaz gráfica (debug)

En `scraper_propiedades.py`, línea 84:

```python
browser = await p.chromium.launch(headless=False)  # Cambiar a False
```

## 📝 Notas

- El scraper está optimizado para sitios con estructura similar a Paraíso Dorado
- Para otros sitios, puede requerir ajustes en los selectores
- Las imágenes se filtran por tamaño (>200px) para evitar logos/iconos

## 🐛 Troubleshooting

### Error: "playwright not found"
```bash
playwright install
```

### Timeout errors
Aumentar timeout en línea 86:
```python
await page.goto(url, wait_until='networkidle', timeout=120000)  # 2 minutos
```

## 📧 Soporte

Para sitios adicionales o problemas, ajusta los selectores en la clase `PropiedadScraper`.

