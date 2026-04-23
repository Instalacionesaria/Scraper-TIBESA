"""
Utilidades para normalizar y validar datos extraídos
"""

import re
from typing import Dict, Any, Optional


class DataNormalizer:
    """Normalizador de datos de propiedades"""
    
    @staticmethod
    def normalizar_precio(precio_texto: str) -> Dict[str, Any]:
        """
        Normaliza el precio extrayendo valor numérico y moneda
        
        Args:
            precio_texto: Texto del precio (ej: "$3,700,000 MXN")
            
        Returns:
            dict: {"precio_raw": str, "precio_numerico": float, "moneda": str}
        """
        resultado = {
            'precio_raw': precio_texto,
            'precio_numerico': None,
            'moneda': None
        }
        
        if not precio_texto:
            return resultado
        
        # Extraer moneda
        if 'MXN' in precio_texto or 'pesos' in precio_texto.lower():
            resultado['moneda'] = 'MXN'
        elif 'USD' in precio_texto or 'dólares' in precio_texto.lower() or 'dolares' in precio_texto.lower():
            resultado['moneda'] = 'USD'
        
        # Extraer valor numérico
        # Buscar patrón: $1,234,567.89 o 1234567
        numeros = re.findall(r'[\d,]+\.?\d*', precio_texto.replace('$', ''))
        if numeros:
            try:
                # Remover comas y convertir a float
                valor = numeros[0].replace(',', '')
                resultado['precio_numerico'] = float(valor)
            except:
                pass
        
        return resultado
    
    @staticmethod
    def normalizar_superficie(texto: str) -> Optional[Dict[str, Any]]:
        """
        Normaliza medidas de superficie
        
        Args:
            texto: Texto con superficie (ej: "450 m²", "9.33 has")
            
        Returns:
            dict: {"valor": float, "unidad": str, "valor_m2": float}
        """
        if not texto:
            return None
        
        # Remover espacios extra
        texto = texto.strip()
        
        # Patrones para diferentes unidades
        patrones = [
            (r'([\d,.]+)\s*m[²2]', 'm2', 1),           # metros cuadrados
            (r'([\d,.]+)\s*has?\.?', 'hectareas', 10000),  # hectáreas a m²
            (r'([\d,.]+)\s*metros', 'metros', 1),       # metros lineales
        ]
        
        for patron, unidad, factor in patrones:
            match = re.search(patron, texto, re.IGNORECASE)
            if match:
                try:
                    valor_str = match.group(1).replace(',', '')
                    valor = float(valor_str)
                    return {
                        'valor': valor,
                        'unidad': unidad,
                        'valor_m2': valor * factor,
                        'texto_original': texto
                    }
                except:
                    pass
        
        return None
    
    @staticmethod
    def normalizar_telefono(telefono: str) -> Optional[str]:
        """
        Normaliza número de teléfono
        
        Args:
            telefono: Texto con teléfono
            
        Returns:
            str: Teléfono normalizado (solo dígitos con guiones)
        """
        if not telefono:
            return None
        
        # Extraer solo dígitos
        digitos = re.sub(r'\D', '', telefono)
        
        # Formatear según longitud
        if len(digitos) == 10:
            # (669) 994-7029 -> 669-994-7029
            return f"{digitos[0:3]}-{digitos[3:6]}-{digitos[6:10]}"
        elif len(digitos) == 12 and digitos.startswith('52'):
            # +52 669 994 7029 -> 669-994-7029
            return f"{digitos[2:5]}-{digitos[5:8]}-{digitos[8:12]}"
        
        return digitos
    
    @staticmethod
    def extraer_id_propiedad(url: str) -> Optional[str]:
        """
        Extrae el ID de la propiedad desde la URL
        
        Args:
            url: URL de la propiedad
            
        Returns:
            str: ID de la propiedad o None
        """
        # Patrones comunes: id273, id-273, propiedad/273, etc.
        patrones = [
            r'id[_-]?(\d+)',
            r'propiedad[/_-](\d+)',
            r'/(\d+)/?$',
        ]
        
        for patron in patrones:
            match = re.search(patron, url, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    @staticmethod
    def limpiar_texto(texto: str) -> str:
        """
        Limpia texto eliminando espacios extra y caracteres especiales
        
        Args:
            texto: Texto a limpiar
            
        Returns:
            str: Texto limpio
        """
        if not texto:
            return ""
        
        # Remover espacios múltiples
        texto = re.sub(r'\s+', ' ', texto)
        
        # Remover saltos de línea extra
        texto = re.sub(r'\n+', '\n', texto)
        
        return texto.strip()
    
    @staticmethod
    def validar_datos_completos(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Valida que los datos críticos estén presentes
        
        Args:
            data: Diccionario con datos de la propiedad
            
        Returns:
            dict: {"valido": bool, "campos_faltantes": list}
        """
        campos_criticos = ['titulo', 'precio', 'ubicacion']
        campos_faltantes = []
        
        for campo in campos_criticos:
            if not data.get(campo):
                campos_faltantes.append(campo)
        
        return {
            'valido': len(campos_faltantes) == 0,
            'campos_faltantes': campos_faltantes,
            'completitud': (len(campos_criticos) - len(campos_faltantes)) / len(campos_criticos) * 100
        }
