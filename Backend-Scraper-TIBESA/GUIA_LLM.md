# 🤖 Guía: Integración con OpenAI LLM

## 🎯 ¿Qué hace el LLM?

El sistema ahora tiene **2 etapas**:

```
1. Scraper (Playwright) → Extrae datos básicos + descripción completa
2. LLM (OpenAI)        → Estructura la descripción en datos organizados
```

---

## 📦 Instalación

### 1. Instalar nuevas dependencias

```bash
pip install openai python-dotenv
```

O reinstalar todo:

```bash
pip install -r requirements.txt
```

### 2. Configurar API Key de OpenAI

```bash
# Copiar template
cp .env.example .env

# Editar .env y agregar tu API key
nano .env
```

En `.env`:

```bash
OPENAI_API_KEY=sk-proj-tu_api_key_aqui
OPENAI_MODEL=gpt-4o-mini
```

**Obtener API Key:**
1. Ve a: https://platform.openai.com/api-keys
2. Crea una nueva key
3. Cópiala al archivo `.env`

---

## 🚀 Uso

### Opción 1: Script de Prueba con LLM

```bash
python test_scraper_llm.py
```

Este script:
1. ✅ Scrapea con Playwright
2. ✅ Procesa con OpenAI
3. ✅ Muestra comparación
4. ✅ Guarda JSON completo

### Opción 2: Uso Programático

```python
from scrapers.paraiso_dorado import ParaisoDoradoScraper
from utils.llm_processor import procesar_propiedad_con_llm
import asyncio

async def scrapear_y_procesar(url):
    # Paso 1: Scrapear
    scraper = ParaisoDoradoScraper()
    datos_scraper = await scraper.extraer_informacion(url)
    
    # Paso 2: Procesar con LLM
    datos_completos = procesar_propiedad_con_llm(datos_scraper)
    
    return datos_completos

# Ejecutar
resultado = asyncio.run(scrapear_y_procesar("https://..."))
```

### Opción 3: Solo LLM (sin scraper)

```python
from utils.llm_processor import LLMProcessor

processor = LLMProcessor()

descripcion = """
Departamento totalmente amueblado
1 recámara, 1 baño
51 m² de construcción
Roof Garden con alberca
"""

datos = processor.estructurar_descripcion(descripcion)
print(datos)
```

---

## 📊 Output del LLM

El LLM extrae y estructura:

```json
{
  "tipo_propiedad": "departamento",
  "construccion": {
    "valor": 51,
    "unidad": "m2"
  },
  "espacios": {
    "recamaras": 1,
    "baños": 1,
    "estacionamientos": null
  },
  "amenidades": [
    "Roof Garden",
    "Alberca exclusiva",
    "Acceso controlado"
  ],
  "caracteristicas": {
    "amueblado": true,
    "cocina_equipada": true,
    "acabados": "alta calidad",
    "estado": "nuevo"
  },
  "descripcion_limpia": "Departamento amueblado listo para habitar con roof garden y alberca exclusiva",
  "_llm_metadata": {
    "model": "gpt-4o-mini",
    "tokens_usados": 450
  }
}
```

---

## 💰 Costos de OpenAI

### Modelos Recomendados

| Modelo | Costo por 1M tokens | Precisión | Velocidad |
|--------|---------------------|-----------|-----------|
| **gpt-4o-mini** | ~$0.15 | ⭐⭐⭐⭐ | ⚡⚡⚡ |
| gpt-4o | ~$2.50 | ⭐⭐⭐⭐⭐ | ⚡⚡ |
| gpt-4-turbo | ~$10 | ⭐⭐⭐⭐⭐ | ⚡ |

**Recomendación:** Usa `gpt-4o-mini` (muy bueno y barato)

### Estimación de Costos

- 1 propiedad ≈ 400-800 tokens
- **gpt-4o-mini**: ~$0.0001 por propiedad
- **100 propiedades**: ~$0.01 USD
- **1000 propiedades**: ~$0.10 USD

💡 **Muy económico!**

---

## 🎨 Comparación: Antes vs Ahora

### ❌ Antes (Solo Scraper)

```json
{
  "tipo_propiedad": "terreno_agricola",  ← INCORRECTO
  "caracteristicas": {
    "agricola": true,  ← FALSO POSITIVO
    "laguna": true     ← CONFUSIÓN
  }
}
```

**Problemas:**
- Detecta "agrícola" del sidebar
- Confunde "alberca" con "laguna"
- No extrae amenidades

### ✅ Ahora (Scraper + LLM)

```json
{
  "tipo_propiedad": "departamento",  ← CORRECTO
  "construccion": {"valor": 51, "unidad": "m2"},
  "amenidades": [
    "Roof Garden",
    "Alberca exclusiva para 5 unidades",
    "Acceso controlado"
  ],
  "caracteristicas": {
    "amueblado": true,
    "cocina_equipada": true,
    "acabados": "alta calidad"
  }
}
```

**Ventajas:**
- ✅ Tipo correcto
- ✅ Amenidades específicas
- ✅ Detalles precisos
- ✅ No confusiones

---

## 🔧 Configuración Avanzada

### Cambiar Modelo

En `.env`:

```bash
# Más barato y rápido (recomendado)
OPENAI_MODEL=gpt-4o-mini

# Más preciso pero caro
OPENAI_MODEL=gpt-4o

# Máxima precisión
OPENAI_MODEL=gpt-4-turbo
```

### Usar en la API

Modifica `main.py` para incluir procesamiento LLM:

```python
from utils.llm_processor import procesar_propiedad_con_llm

@app.post("/scrape")
async def scrape_property(request: ScrapeRequest, use_llm: bool = True):
    # Scrapear
    datos = await scraper.extraer_informacion(str(request.url))
    
    # Procesar con LLM si se solicita
    if use_llm:
        datos = procesar_propiedad_con_llm(datos)
    
    return ScrapeResponse(success=True, data=datos)
```

---

## 🐛 Solución de Problemas

### Error: "No se encontró API key"

```bash
# Verificar que existe .env
ls -la .env

# Verificar contenido
cat .env

# Debe contener:
OPENAI_API_KEY=sk-proj-...
```

### Error: "Invalid API key"

- Verifica que la key sea correcta
- Verifica que tenga créditos en OpenAI
- Revisa en: https://platform.openai.com/account/billing

### Error: "Rate limit"

- Has excedido el límite de requests
- Espera unos minutos
- Considera upgrader tu plan en OpenAI

---

## 📚 Ejemplos de Casos de Uso

### 1. Procesar 100 propiedades

```python
urls = [...]  # Lista de URLs

for url in urls:
    datos = await scrapear_y_procesar(url)
    guardar_en_base_de_datos(datos)
```

### 2. Solo procesar descripciones existentes

```python
# Si ya tienes JSONs sin procesar
import json

with open('propiedad.json') as f:
    datos = json.load(f)

datos_procesados = procesar_propiedad_con_llm(datos)
```

### 3. Mejorar descripciones

```python
from utils.llm_processor import LLMProcessor

processor = LLMProcessor()
descripcion_mejorada = processor.mejorar_descripcion(descripcion_original)
```

---

## ✅ Checklist de Configuración

- [ ] Instalar dependencias (`pip install -r requirements.txt`)
- [ ] Copiar `.env.example` a `.env`
- [ ] Agregar `OPENAI_API_KEY` en `.env`
- [ ] Verificar créditos en OpenAI
- [ ] Probar con `python test_scraper_llm.py`
- [ ] Verificar que se genera JSON con `datos_llm`

---

## 🎉 ¡Listo!

Ahora tienes un sistema completo:
- ✅ Scraper extrae HTML
- ✅ LLM estructura datos
- ✅ Datos precisos y completos
- ✅ Funciona con cualquier formato de descripción

**Siguiente paso:** Crea tu archivo `.env` y prueba el sistema! 🚀
