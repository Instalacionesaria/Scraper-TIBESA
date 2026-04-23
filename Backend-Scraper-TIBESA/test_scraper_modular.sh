#!/bin/bash

# Script para probar el nuevo sistema modular de scrapers
# Prueba el scraper de Paraíso Dorado

echo "======================================"
echo "🧪 PRUEBA DEL SISTEMA MODULAR"
echo "======================================"
echo ""

# Verificar que estamos en el directorio correcto
if [ ! -f "test_paraiso_dorado.py" ]; then
    echo "❌ Error: Ejecuta este script desde el directorio raíz del proyecto"
    exit 1
fi

# Verificar Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python3 no está instalado"
    exit 1
fi

echo "✓ Python encontrado: $(python3 --version)"
echo ""

# Verificar dependencias
echo "📦 Verificando dependencias..."
python3 -c "import playwright" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  Playwright no está instalado"
    echo "   Instalando dependencias..."
    pip install -r requirements.txt
    playwright install chromium
fi

echo "✓ Dependencias verificadas"
echo ""

# Ejecutar prueba
echo "======================================"
echo "🚀 EJECUTANDO PRUEBA"
echo "======================================"
echo ""

python3 test_paraiso_dorado.py

# Verificar resultado
if [ $? -eq 0 ]; then
    echo ""
    echo "======================================"
    echo "✅ PRUEBA COMPLETADA EXITOSAMENTE"
    echo "======================================"
    echo ""
    echo "📁 Archivos generados:"
    echo "   • JSON: data/json/"
    echo "   • Imágenes: data/imagenes/"
    echo ""
    ls -lh data/json/ | tail -n 5
else
    echo ""
    echo "======================================"
    echo "❌ LA PRUEBA FALLÓ"
    echo "======================================"
    exit 1
fi
