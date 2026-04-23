#!/bin/bash

# Script para iniciar la API rápidamente

ENV_NAME="ARIA-TIBESA-Scraper-2"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║                                                          ║"
echo "║     🚀  API SCRAPER DE PROPIEDADES                      ║"
echo "║                                                          ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Verificar que conda esté disponible
if ! command -v conda &> /dev/null; then
    echo "❌ Conda no encontrado"
    exit 1
fi

# Verificar que el entorno existe
if ! conda env list | grep -q "^${ENV_NAME} "; then
    echo "❌ El entorno '${ENV_NAME}' no existe."
    echo "Ejecuta primero: ./setup.sh"
    exit 1
fi

# Activar entorno
echo "🔧 Activando entorno ${ENV_NAME}..."
source $(conda info --base)/etc/profile.d/conda.sh
conda activate ${ENV_NAME}

# Verificar activación
if [[ "$CONDA_DEFAULT_ENV" != "$ENV_NAME" ]]; then
    echo "❌ Error al activar el entorno"
    exit 1
fi

echo "✓ Entorno activado"
echo ""

# Verificar que FastAPI esté instalado
if ! python -c "import fastapi" 2>/dev/null; then
    echo "⚠️  FastAPI no está instalado"
    echo "Instalando dependencias de la API..."
    pip install fastapi uvicorn python-multipart
    echo ""
fi

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  📡 INICIANDO SERVIDOR API                               ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "🌐 API disponible en:"
echo "   → http://localhost:8000"
echo ""
echo "📖 Documentación Swagger:"
echo "   → http://localhost:8000/docs"
echo ""
echo "📋 Endpoints principales:"
echo "   → POST   /scrape          (Scrapear propiedad)"
echo "   → GET    /properties      (Listar propiedades)"
echo "   → GET    /property/{id}   (Obtener propiedad)"
echo "   → GET    /images/{file}   (Servir imagen)"
echo ""
echo "⏹️  Presiona Ctrl+C para detener el servidor"
echo ""
echo "─────────────────────────────────────────────────────────────"
echo ""

# Iniciar servidor
python main.py



