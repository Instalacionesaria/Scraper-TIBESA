"""
Procesador LLM para Descripciones de Propiedades
Usa LangChain 1.0 con init_chat_model para extraer y estructurar información
"""

import os
import json
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage

# Cargar variables de entorno
load_dotenv()


# ========================================
# MODELOS PYDANTIC PARA STRUCTURED OUTPUT
# ========================================

class Construccion(BaseModel):
    """Datos de construcción de la propiedad"""
    metros_cuadrados: Optional[float] = Field(None, description="Metros cuadrados de construcción")
    niveles: Optional[int] = Field(None, description="Número de niveles/pisos")
    año_construccion: Optional[int] = Field(None, description="Año de construcción")
    estado_construccion: Optional[str] = Field(None, description="nuevo, seminuevo, usado, remodelado, a_remodelar, en_construccion")


class Terreno(BaseModel):
    """Datos del terreno"""
    metros_cuadrados: Optional[float] = Field(None, description="Metros cuadrados del terreno")
    hectareas: Optional[float] = Field(None, description="Hectáreas (si aplica)")
    frente_metros: Optional[float] = Field(None, description="Metros de frente")
    fondo_metros: Optional[float] = Field(None, description="Metros de fondo")
    forma: Optional[str] = Field(None, description="regular, irregular, esquina")
    uso_de_suelo: Optional[str] = Field(None, description="residencial, comercial, mixto, industrial, agricola")


class EspaciosInteriores(BaseModel):
    """Espacios interiores de la propiedad"""
    recamaras: Optional[int] = Field(None, description="Número de recámaras")
    baños_completos: Optional[int] = Field(None, description="Número de baños completos")
    medios_baños: Optional[int] = Field(None, description="Número de medios baños")
    cocina_integral: Optional[bool] = Field(None)
    sala: Optional[bool] = Field(None)
    comedor: Optional[bool] = Field(None)
    estudio: Optional[bool] = Field(None)
    cuarto_servicio: Optional[bool] = Field(None)
    balcon: Optional[bool] = Field(None)
    terraza: Optional[bool] = Field(None)
    patio: Optional[bool] = Field(None)
    area_lavado: Optional[bool] = Field(None)


class Estacionamiento(BaseModel):
    """Datos de estacionamiento"""
    tiene: Optional[bool] = Field(None)
    espacios: Optional[int] = Field(None, description="Número de espacios")
    tipo: Optional[str] = Field(None, description="techado, descubierto, subterraneo, cajon_asignado")


class Amenidades(BaseModel):
    """Amenidades del edificio/desarrollo"""
    alberca: Optional[bool] = Field(None)
    gimnasio: Optional[bool] = Field(None)
    roof_garden: Optional[bool] = Field(None)
    elevador: Optional[bool] = Field(None)
    seguridad_24h: Optional[bool] = Field(None)
    acceso_controlado: Optional[bool] = Field(None)
    area_juegos: Optional[bool] = Field(None)
    area_asadores: Optional[bool] = Field(None)
    jardines: Optional[bool] = Field(None)
    pet_friendly: Optional[bool] = Field(None)


class UbicacionVentajas(BaseModel):
    """Ventajas de ubicación"""
    zona: Optional[str] = Field(None, description="Nombre/descripción de la zona")
    colonia: Optional[str] = Field(None, description="Colonia o fraccionamiento")
    cerca_de: Optional[List[str]] = Field(None, description="Lugares cercanos relevantes")
    vista: Optional[str] = Field(None, description="mar, ciudad, montaña, jardin, calle")
    frente_a_carretera: Optional[bool] = Field(None)


class AnalisisMercado(BaseModel):
    """Análisis de mercado de la propiedad"""
    segmento: Optional[str] = Field(None, description="economico, medio, residencial, premium, lujo")
    target: Optional[str] = Field(None, description="jovenes, familias, inversionistas, jubilados, empresarios")
    uso_recomendado: Optional[List[str]] = Field(None, description="vivienda, inversion, renta, vacacional, comercial")


class PropiedadEstructurada(BaseModel):
    """Modelo completo de una propiedad analizada por el LLM"""
    tipo_propiedad: str = Field(description="casa, departamento, condominio, terreno, terreno_agricola, local_comercial, bodega, edificio, lote, rancho")

    construccion: Optional[Construccion] = Field(None)
    terreno: Optional[Terreno] = Field(None)
    espacios_interiores: Optional[EspaciosInteriores] = Field(None)
    estacionamiento: Optional[Estacionamiento] = Field(None)
    amenidades: Optional[Amenidades] = Field(None)
    ubicacion_ventajas: Optional[UbicacionVentajas] = Field(None)
    analisis_mercado: Optional[AnalisisMercado] = Field(None)

    destacados_venta: List[str] = Field(description="3-5 puntos clave para vender la propiedad")
    descripcion_comercial: str = Field(description="Descripción atractiva de 2-3 líneas para el comprador")
    notas_importantes: Optional[str] = Field(None, description="Info adicional relevante")


# ========================================
# PROCESADOR LLM CON LANGCHAIN
# ========================================

class LLMProcessor:
    """Procesa descripciones de propiedades usando LangChain con init_chat_model"""

    def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None):
        """
        Inicializa el procesador LLM con LangChain

        Args:
            model_name: Nombre del modelo (default: valor de .env o gpt-4o-mini)
            api_key: API key de OpenAI (default: valor de .env)
        """
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        self.model_name = model_name or os.getenv('OPENAI_MODEL', 'gpt-4o-mini')

        if not self.api_key:
            raise ValueError(
                "No se encontró API key de OpenAI. "
                "Configura OPENAI_API_KEY en .env o pásala como parámetro."
            )

        # Inicializar modelo con LangChain 1.0
        self.llm = init_chat_model(
            self.model_name,
            model_provider="openai",
            api_key=self.api_key,
            temperature=0
        )

        # LLM con structured output (Pydantic)
        self.llm_structured = self.llm.with_structured_output(PropiedadEstructurada)

        self.system_prompt = """Eres un experto analista inmobiliario en México, especializado en Mazatlán, Sinaloa.

Tu trabajo es analizar la información de una propiedad inmobiliaria y extraer TODOS los datos relevantes de forma estructurada.

REGLAS:
- Extrae CADA dato mencionado en el título, ubicación y descripción
- Si algo no está mencionado, usa null (NUNCA inventes datos)
- Sé preciso con números y medidas
- Diferencia entre construcción y terreno
- Identifica el tipo EXACTO de propiedad basándote en el título y descripción
- Los destacados_venta deben ser concisos y atractivos para un comprador
- La descripcion_comercial debe ser profesional y en español

TIPOS DE PROPIEDAD:
- casa: vivienda unifamiliar
- departamento: dentro de un edificio de departamentos
- condominio: unidad dentro de un desarrollo/complejo
- terreno: lote sin construcción
- terreno_agricola: tierra para agricultura/ganadería
- local_comercial: espacio para negocio
- bodega: almacén/nave industrial
- edificio: edificio completo
- lote: lote residencial
- rancho: propiedad rural grande"""

    def estructurar_propiedad(self, descripcion: str, datos_basicos: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Procesa una propiedad y extrae datos estructurados usando structured output

        Args:
            descripcion: Texto de la descripción de la propiedad
            datos_basicos: Datos ya extraídos por el scraper (titulo, ubicacion, precio)

        Returns:
            dict: Datos estructurados extraídos
        """
        # Construir el contexto
        contexto = ""
        if datos_basicos:
            contexto = f"""DATOS YA EXTRAÍDOS POR EL SCRAPER:
- Título: {datos_basicos.get('titulo', 'N/A')}
- Ubicación: {datos_basicos.get('ubicacion', 'N/A')}
- Precio: {datos_basicos.get('precio', 'N/A')}
- Estado: {datos_basicos.get('estado', 'N/A')}
"""

        user_content = f"""{contexto}
DESCRIPCIÓN DE LA PROPIEDAD:
{descripcion}

Analiza toda la información y extrae los datos estructurados."""

        try:
            # Llamar al LLM con structured output
            resultado: PropiedadEstructurada = self.llm_structured.invoke([
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=user_content)
            ])

            # Convertir Pydantic a dict
            resultado_dict = resultado.model_dump(exclude_none=True)

            # Agregar metadata del modelo
            resultado_dict['_llm_metadata'] = {
                'model': self.model_name,
                'provider': 'openai',
                'framework': 'langchain'
            }

            return resultado_dict

        except Exception as e:
            print(f"❌ Error al procesar con LLM: {e}")
            return {"error": str(e)}

    def mejorar_descripcion(self, descripcion: str) -> str:
        """
        Limpia y mejora una descripción para hacerla más profesional

        Args:
            descripcion: Descripción original

        Returns:
            str: Descripción mejorada
        """
        try:
            response = self.llm.invoke([
                SystemMessage(content="Eres un editor experto en textos inmobiliarios en México."),
                HumanMessage(content=f"""Limpia y mejora esta descripción de propiedad:

{descripcion}

INSTRUCCIONES:
1. Elimina texto duplicado
2. Corrige errores de formato
3. Organiza en párrafos cortos
4. Mantén toda la información relevante
5. Hazla profesional pero natural
6. Máximo 250 palabras

Devuelve SOLO la descripción mejorada.""")
            ])

            return response.content.strip()

        except Exception as e:
            print(f"⚠️ Error al mejorar descripción: {e}")
            return descripcion


def procesar_propiedad_con_llm(datos_scraper: Dict[str, Any]) -> Dict[str, Any]:
    """
    Función helper para procesar datos del scraper con LLM

    Args:
        datos_scraper: Datos extraídos por el scraper

    Returns:
        dict: Datos combinados (scraper + LLM)
    """
    processor = LLMProcessor()

    # Extraer descripción
    descripcion = datos_scraper.get('descripcion', '')

    if not descripcion:
        print("⚠️ No hay descripción para procesar")
        return datos_scraper

    print("🤖 Procesando con LLM (LangChain)...")

    # Estructurar con LLM
    datos_llm = processor.estructurar_propiedad(
        descripcion=descripcion,
        datos_basicos={
            'titulo': datos_scraper.get('titulo'),
            'ubicacion': datos_scraper.get('ubicacion'),
            'precio': datos_scraper.get('precio'),
            'estado': datos_scraper.get('estado')
        }
    )

    # Combinar datos
    datos_combinados = {
        **datos_scraper,
        'analisis_llm': datos_llm,
        'procesado_con_llm': True
    }

    # Sobrescribir tipo si LLM tiene uno mejor
    if datos_llm.get('tipo_propiedad'):
        datos_combinados['tipo_propiedad'] = datos_llm['tipo_propiedad']

    model_name = datos_llm.get('_llm_metadata', {}).get('model', 'N/A')
    print(f"✅ LLM completado (modelo: {model_name})")

    return datos_combinados


if __name__ == "__main__":
    # Ejemplo de uso
    processor = LLMProcessor()

    ejemplo_descripcion = """
    Local Comercial
    Ubicado sobre Av. Gutiérrez Nájera, a pie de calle y con excelente visibilidad.
    Una oportunidad ideal para emprender o expandir tu negocio en una zona estratégica
    y de alto flujo peatonal. Perfecto para:
    Cafetería, Boutique de ropa, Artesanías, Jugos y snacks, Punto de distribución.
    Espacio versátil, listo para adaptarse a tu concepto comercial.
    """

    resultado = processor.estructurar_propiedad(
        ejemplo_descripcion,
        datos_basicos={
            'titulo': 'LOCAL COMERCIAL EN PLAZA NAJERA MAZATLÁN SINALOA',
            'ubicacion': 'PLAZA NAJERA, MAZATLAN, Sinaloa.',
            'precio': '$480,000 MXN',
            'estado': 'EN VENTA'
        }
    )

    print("\n📊 Resultado:")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
