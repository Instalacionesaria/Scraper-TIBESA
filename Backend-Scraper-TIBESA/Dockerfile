# Imagen oficial de Playwright con Python: trae Chromium + deps del SO
FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

WORKDIR /app

# Instalar dependencias primero (aprovecha cache de Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Carpeta de datos (se monta como volumen persistente en EasyPanel)
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
