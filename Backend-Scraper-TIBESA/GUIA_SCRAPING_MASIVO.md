# 🚀 Guía de Scraping Masivo - Paraíso Dorado

Esta guía explica cómo scrapear **TODOS** los inmuebles del sitio de Paraíso Dorado de manera eficiente y automatizada.

---

## 📋 Opciones Disponibles

### 1️⃣ **Scraping Automático Completo** (Recomendado)
Escanea todo el sitio automáticamente y scrapeaq todas las propiedades encontradas.

```bash
python scrape_all_paraiso_dorado.py
```

**Características:**
- ✅ Detecta automáticamente TODAS las propiedades del sitio
- ✅ Navega por todas las páginas de listado
- ✅ Encuentra la paginación automáticamente
- ✅ Evita duplicados
- ✅ Muestra progreso en tiempo real
- ✅ Genera estadísticas completas

**¿Cuándo usar esto?**
- Cuando quieres scrapear TODO el sitio sin preocuparte por las URLs
- Primera vez que scrapeas el sitio
- Quieres mantener una base de datos completa actualizada

---

### 2️⃣ **Scraping de Lista Específica**
Scrapeaq solo las URLs que tú especifiques.

```bash
python scrape_urls_list.py
```

**Antes de ejecutar**, edita el archivo y agrega tus URLs:

```python
urls_a_scrapear = [
    "https://paraisodorado.com.mx/es/propiedad/departamento-en-brisas-del-vigia-id275",
    "https://paraisodorado.com.mx/es/propiedad/otra-propiedad-id123",
    # Agrega más URLs aquí...
]
```

**¿Cuándo usar esto?**
- Ya tienes una lista específica de propiedades
- Quieres re-scrapear propiedades específicas
- Necesitas actualizar datos de ciertas propiedades

---

### 3️⃣ **Scraping Individual** (Para pruebas)
Scrapeaq una sola propiedad.

```bash
python test_paraiso_dorado.py
```

**¿Cuándo usar esto?**
- Pruebas y desarrollo
- Verificar que el scraper funciona correctamente
- Inspeccionar datos de una propiedad específica

---

### 4️⃣ **Test de Organización por Carpetas** (Demostración)
Scrapeaq 2-3 propiedades y muestra la estructura de carpetas.

```bash
python test_carpetas_organizadas.py
```

**¿Cuándo usar esto?**
- Ver cómo se organizan las imágenes por carpetas
- Verificar la nueva estructura antes del scraping masivo
- Entender la organización del sistema

---

## ⚙️ Configuración

### Parámetros Principales

```python
# Directorio donde se guardarán los datos
OUTPUT_DIR = "data"

# Modo headless (sin ventana del navegador)
HEADLESS = True  # True = sin ventana, False = ver navegador

# Delay entre requests (en segundos)
DELAY = 2.0  # Ser respetuoso con el servidor
```

### Modificar Configuración

#### Ver el navegador en acción:
```python
HEADLESS = False
```

#### Aumentar velocidad (no recomendado):
```python
DELAY = 1.0  # Mínimo recomendado
```

#### Cambiar directorio de salida:
```python
OUTPUT_DIR = "mis_datos"
```

---

## 📂 Estructura de Salida

Después de ejecutar el scraping, encontrarás:

```
data/
├── json/
│   ├── paraiso_dorado_275_20260106_123456.json
│   ├── paraiso_dorado_153_20260106_123458.json
│   └── ... (un archivo JSON por propiedad)
│
└── imagenes/
    ├── propiedad_275/
    │   ├── imagen_20260106_123456_1.webp
    │   ├── imagen_20260106_123456_2.webp
    │   └── ... (todas las imágenes de esta propiedad)
    │
    ├── propiedad_153/
    │   ├── imagen_20260106_123458_1.webp
    │   ├── imagen_20260106_123458_2.webp
    │   └── ... (todas las imágenes de esta propiedad)
    │
    └── ... (una carpeta por propiedad)
```

### Formato de Organización

- **JSON**: `paraiso_dorado_{ID}_{FECHA}_{HORA}.json`
- **Carpetas de Imágenes**: `propiedad_{ID}/`
- **Imágenes**: `imagen_{FECHA}_{HORA}_{NUM}.webp`

Donde:
- `{ID}` = ID de la propiedad (ej: 275, 153)
- `{FECHA}` = Fecha de scraping (YYYYMMDD)
- `{HORA}` = Hora de scraping (HHMMSS)
- `{NUM}` = Número de imagen (1, 2, 3...)

### ✨ Ventajas de la Organización por Carpetas

✅ **Fácil identificación**: Cada carpeta contiene solo las imágenes de una propiedad  
✅ **Nombres simples**: Los archivos se llaman `imagen_1.webp`, `imagen_2.webp`, etc.  
✅ **Gestión sencilla**: Puedes copiar, mover o respaldar carpetas completas  
✅ **ID en carpeta**: El nombre de la carpeta indica el ID de la propiedad  
✅ **Escalable**: Funciona bien con 10 o 1000 propiedades

---

## 📊 Ejemplo de Salida

### Mientras se ejecuta:

```
================================================================================
🔍 EXTRAYENDO URLS DE PROPIEDADES
================================================================================

📄 Página 1/3: https://paraisodorado.com.mx/es/propiedades
   ✓ Enlaces encontrados en esta página: 24
   ✓ URLs únicas acumuladas: 24

📄 Página 2/3: https://paraisodorado.com.mx/es/propiedades?page=2
   ✓ Enlaces encontrados en esta página: 24
   ✓ URLs únicas acumuladas: 48

✅ Total de propiedades encontradas: 71

================================================================================
🚀 INICIANDO SCRAPING MASIVO
================================================================================

📊 Total de propiedades a scrapear: 71
⏱️  Delay entre requests: 2.0s
📁 Directorio de salida: data

================================================================================
🏠 Propiedad 1/71 (1.4%)
================================================================================
🔗 URL: https://paraisodorado.com.mx/es/propiedad/...

🌐 Navegando a la URL...
📝 Extrayendo datos básicos...
🏢 Empresa: Paraíso Dorado
📐 Extrayendo datos del terreno/propiedad...
🏠 Extrayendo tipo de propiedad...
✨ Extrayendo características...
👤 Extrayendo información del agente...
🖼️  Extrayendo imágenes...

📋 Resumen:
   • Título: Departamento en Brisas del Vigía
   • Precio: $3,000,000 MXN
   • Tipo: Departamento
   • Imágenes: 19

✅ Propiedad 1 scrapeada exitosamente!

⏳ Esperando 2.0s antes de la siguiente...
```

### Al finalizar:

```
================================================================================
📊 ESTADÍSTICAS FINALES
================================================================================

🔍 Propiedades encontradas: 71
🚀 Propiedades scrapeadas: 71
✅ Exitosas: 69
❌ Fallidas: 2
⏱️  Duración total: 0:04:32
📁 Archivos guardados en: data/json/
🖼️  Imágenes guardadas en: data/imagenes/

📈 Tasa de éxito: 97.2%

================================================================================
🏁 SCRAPING MASIVO COMPLETADO
================================================================================
```

---

## 🎯 Casos de Uso

### Caso 1: Primera vez - Scrapear TODO
```bash
# 1. Ejecutar scraping masivo
python scrape_all_paraiso_dorado.py

# 2. Revisar resultados
ls -la data/json/
ls -la data/imagenes/

# 3. Verificar estadísticas en la salida del terminal
```

### Caso 2: Actualizar propiedades específicas
```bash
# 1. Editar scrape_urls_list.py con las URLs deseadas
# 2. Ejecutar
python scrape_urls_list.py
```

### Caso 3: Mantener base de datos actualizada
```bash
# Ejecutar periódicamente (ej: cada semana)
python scrape_all_paraiso_dorado.py
```

---

## ⏱️ Tiempos Estimados

Considerando:
- **71 propiedades** (aproximado)
- **Delay de 2 segundos** entre requests
- **~8-12 segundos** por propiedad (scraping + descarga de imágenes)

**Tiempo total estimado:** 10-15 minutos

| Propiedades | Delay | Tiempo Estimado |
|-------------|-------|-----------------|
| 71          | 2s    | ~10-15 min      |
| 71          | 1s    | ~8-12 min       |
| 100         | 2s    | ~15-20 min      |

---

## 🔧 Solución de Problemas

### Problema: "No se encontraron propiedades"
**Solución:**
1. Verificar conexión a internet
2. Verificar que el sitio esté accesible
3. Ejecutar con `HEADLESS = False` para ver qué pasa

### Problema: Muchas propiedades fallan
**Solución:**
1. Aumentar el `DELAY` a 3-5 segundos
2. Verificar logs de errores en la salida
3. Ejecutar con `HEADLESS = False` para debuggear

### Problema: Proceso muy lento
**Causas normales:**
- Descarga de muchas imágenes (normal)
- Conexión lenta a internet
- Sitio web lento

**Opciones:**
- Ser paciente (es normal)
- Desactivar descarga de imágenes temporalmente (modificar scraper)

### Problema: Se interrumpe el proceso
**Solución:**
- Los datos ya scrapeados están guardados
- Re-ejecutar el script (evitará duplicados por las marcas de tiempo)
- O crear una lista de URLs pendientes y usar `scrape_urls_list.py`

---

## 📈 Mejores Prácticas

1. **Respetar el servidor**: Usa un delay de al menos 2 segundos
2. **Ejecutar en horarios de baja demanda**: Preferiblemente fuera de horario laboral
3. **Monitorear la primera ejecución**: Usa `HEADLESS = False` la primera vez
4. **Backup de datos**: Respalda los archivos JSON e imágenes periódicamente
5. **Logs**: Guarda la salida del terminal para referencia

---

## 🎓 Comandos Útiles

### Ver propiedades scrapeadas
```bash
ls -l data/json/ | wc -l
```

### Ver carpetas de propiedades (imágenes)
```bash
ls -d data/imagenes/*/
```

### Contar imágenes de cada propiedad
```bash
for dir in data/imagenes/*/; do echo "$dir: $(ls $dir | wc -l) imágenes"; done
```

### Ver imágenes de una propiedad específica
```bash
ls -la data/imagenes/propiedad_275/
```

### Total de imágenes descargadas
```bash
find data/imagenes -type f | wc -l
```

### Buscar una propiedad específica
```bash
grep -r "Brisas del Vigía" data/json/
```

### Contar propiedades por tipo
```bash
grep -h "tipo_propiedad" data/json/*.json | sort | uniq -c
```

### Copiar imágenes de una propiedad específica
```bash
cp -r data/imagenes/propiedad_275 /ruta/destino/
```

### Listar propiedades con más imágenes
```bash
for dir in data/imagenes/*/; do echo "$(ls $dir | wc -l) - $dir"; done | sort -rn | head -10
```

---

## 🚨 Importante

- ⚠️ El scraping masivo puede tomar tiempo (10-15+ minutos)
- ⚠️ No interrumpir el proceso bruscamente (Ctrl+C está OK)
- ⚠️ Los datos se guardan en tiempo real (no se pierden si se interrumpe)
- ⚠️ Ser respetuoso con el servidor (usar delays adecuados)
- ⚠️ Verificar la legalidad del scraping según términos del sitio

---

## 📞 Soporte

Si encuentras problemas:
1. Revisar esta guía
2. Verificar logs de errores en la salida
3. Ejecutar con `HEADLESS = False` para debuggear visualmente
4. Revisar el código fuente para entender el flujo

---

## 🔄 Actualización de Datos

Para mantener los datos actualizados:

```bash
# Opción 1: Re-scrapear todo (recomendado mensualmente)
python scrape_all_paraiso_dorado.py

# Opción 2: Scrapear solo propiedades nuevas
# (requiere implementar lógica de detección de propiedades ya scrapeadas)
```

---

## ✅ Checklist

Antes de ejecutar el scraping masivo:

- [ ] Conexión a internet estable
- [ ] Espacio en disco suficiente (~500MB-1GB para 71 propiedades)
- [ ] Python y dependencias instaladas
- [ ] Configuración revisada (OUTPUT_DIR, DELAY, etc.)
- [ ] Terminal con buena visibilidad para monitorear progreso
- [ ] Tiempo disponible (~15-20 minutos)

---

**¡Listo para scrapear! 🚀**

```bash
python scrape_all_paraiso_dorado.py
```

