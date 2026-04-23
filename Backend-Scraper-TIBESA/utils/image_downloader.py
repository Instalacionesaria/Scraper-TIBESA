"""
Utilidades para descarga de imágenes
Maneja la descarga asíncrona de imágenes de propiedades
"""

import aiohttp
import os
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
from typing import List, Optional


class ImageDownloader:
    """Manejador de descarga de imágenes"""
    
    def __init__(self, output_dir: str = "data/imagenes"):
        """
        Inicializa el descargador de imágenes
        
        Args:
            output_dir: Directorio donde se guardarán las imágenes
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    async def descargar_imagen(self, session: aiohttp.ClientSession, url: str, 
                               nombre_archivo: Optional[str] = None,
                               carpeta_propiedad: Optional[str] = None) -> Optional[str]:
        """
        Descarga una imagen de forma asíncrona
        
        Args:
            session: Sesión aiohttp
            url: URL de la imagen
            nombre_archivo: Nombre personalizado del archivo (opcional)
            carpeta_propiedad: Subcarpeta específica para la propiedad (opcional)
            
        Returns:
            str: Ruta del archivo guardado o None si falló
        """
        try:
            async with session.get(url, timeout=30) as response:
                if response.status == 200:
                    content = await response.read()
                    
                    # Generar nombre si no se proporciona
                    if not nombre_archivo:
                        ext = os.path.splitext(urlparse(url).path)[1] or '.jpg'
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                        nombre_archivo = f"img_{timestamp}{ext}"
                    
                    # Determinar directorio de destino
                    if carpeta_propiedad:
                        # Crear carpeta específica para esta propiedad
                        destino_dir = self.output_dir / carpeta_propiedad
                        destino_dir.mkdir(parents=True, exist_ok=True)
                    else:
                        destino_dir = self.output_dir
                    
                    filepath = destino_dir / nombre_archivo
                    with open(filepath, 'wb') as f:
                        f.write(content)
                    
                    print(f"   ✓ Imagen descargada: {nombre_archivo}")
                    return str(filepath)
                else:
                    print(f"   ✗ Error al descargar {url}: Status {response.status}")
                    return None
        except Exception as e:
            print(f"   ✗ Error al descargar {url}: {str(e)}")
            return None
    
    async def descargar_multiples(self, urls: List[str], 
                                  prefijo: str = "img",
                                  carpeta_propiedad: Optional[str] = None) -> List[str]:
        """
        Descarga múltiples imágenes en paralelo
        
        Args:
            urls: Lista de URLs de imágenes
            prefijo: Prefijo para los nombres de archivo
            carpeta_propiedad: Subcarpeta específica para la propiedad (opcional)
            
        Returns:
            list: Lista de rutas de archivos descargados exitosamente
        """
        if not urls:
            return []
        
        carpeta_info = f" en carpeta '{carpeta_propiedad}'" if carpeta_propiedad else ""
        print(f"\n📥 Descargando {len(urls)} imágenes{carpeta_info}...")
        
        async with aiohttp.ClientSession() as session:
            tasks = []
            for idx, url in enumerate(urls, 1):
                # Generar nombre único
                ext = os.path.splitext(urlparse(url).path)[1] or '.jpg'
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                nombre = f"{prefijo}_{timestamp}_{idx}{ext}"
                
                tasks.append(self.descargar_imagen(session, url, nombre, carpeta_propiedad))
            
            # Descargar todas en paralelo
            resultados = await asyncio.gather(*tasks)
            imagenes_descargadas = [r for r in resultados if r]
            
            print(f"✓ {len(imagenes_descargadas)}/{len(urls)} imágenes descargadas exitosamente\n")
            return imagenes_descargadas


# Importar asyncio para gather
import asyncio
