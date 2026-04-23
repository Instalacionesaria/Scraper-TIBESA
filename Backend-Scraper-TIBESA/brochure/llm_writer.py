"""
LLM Writer: genera el copy emocional/narrativo de los slides que lo requieren,
alimentado con las estadísticas reales calculadas por el analyzer.

Slides generados por LLM:
  - 1  Portada emocional (título + subtítulo)
  - 2  Storytelling (narrativa de transformación)
  - 3  ¿Por qué Mazatlán? (4 razones + frase ancla)
  - 12 Tendencias (4 bullets)
  - 13 Riesgo vs Oportunidad (2 columnas)
"""

from __future__ import annotations

import json
import os
from typing import Optional

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage


# ========================================
# Fallbacks si el LLM falla / no hay API key
# ========================================

FALLBACK_COPY = {
    "portada": {
        "titulo": "Invierte donde el crecimiento ya comenzó",
        "subtitulo": "Mazatlán: el nuevo polo inmobiliario del Pacífico",
    },
    "storytelling": (
        "Mazatlán está viviendo una transformación. "
        "Lo que antes era un destino turístico tradicional, hoy es un mercado inmobiliario "
        "en expansión, impulsado por inversión, turismo internacional y desarrollo urbano. "
        "Aquí es donde los inversionistas están entrando."
    ),
    "razones": {
        "lista": [
            "Destino turístico consolidado",
            "Crecimiento inmobiliario sostenido",
            "Inversión extranjera creciente",
            "Desarrollo vertical en expansión",
        ],
        "frase_clave": "El valor del suelo aún no alcanza su punto máximo.",
    },
    "tendencias": [
        "Crecimiento hacia el norte",
        "Mayor inversión extranjera",
        "Desarrollo vertical",
        "Incremento en rentas vacacionales",
    ],
    "riesgos": ["Saturación en zonas premium", "Variación de precios"],
    "oportunidades": ["Entrada temprana en expansión", "Plusvalía acelerada"],
}


class BrochureLLMWriter:
    """Genera el copy emocional del brochure a partir de stats reales."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_name = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self._llm = None

    @property
    def llm(self):
        if self._llm is None and self.api_key:
            self._llm = init_chat_model(
                self.model_name,
                model_provider="openai",
                api_key=self.api_key,
                temperature=0.6,
            )
        return self._llm

    # ----------------------------------------
    # Helpers
    # ----------------------------------------

    def _invoke_json(self, system: str, user: str) -> Optional[dict]:
        """Llama al LLM pidiendo JSON estricto. Devuelve None si falla."""
        if not self.llm:
            return None
        try:
            response = self.llm.invoke([
                SystemMessage(content=system + "\n\nResponde SOLO con un objeto JSON válido, sin ```."),
                HumanMessage(content=user),
            ])
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()
            return json.loads(content)
        except Exception as e:
            print(f"[llm_writer] Error: {e}")
            return None

    # ----------------------------------------
    # Generadores por slide
    # ----------------------------------------

    def generar_todo(self, datos: dict) -> dict:
        """
        Genera todos los copies que necesita el brochure de una sola vez
        (una llamada al LLM para minimizar latencia y coste).
        """
        resumen = datos["resumen"]
        por_zona = datos["por_zona"]

        # Resumen compacto para el prompt
        stats = {
            "total_propiedades_analizadas": resumen["total_propiedades"],
            "precio_promedio": resumen["precio"]["media"],
            "precio_m2_terreno_promedio": resumen["precio_m2_terreno"]["media"],
            "precio_m2_construccion_promedio": resumen["precio_m2_construccion"]["media"],
            "zonas": {
                nombre: {
                    "count": s["count"],
                    "precio_medio": s["precio"]["media"],
                    "precio_m2_terreno": s["precio_m2_terreno"]["media"],
                    "precio_m2_construccion": s["precio_m2_construccion"]["media"],
                }
                for nombre, s in por_zona.items()
                if nombre != "Sin clasificar" and s["count"] > 0
            },
        }

        system = (
            "Eres un redactor senior de brochures inmobiliarios premium "
            "para inversionistas en Mazatlán, Sinaloa, México. "
            "Redactas para TIBESA Bienes Raíces, una inmobiliaria establecida. "
            "Tu tono es sobrio, profesional, aspiracional y basado en datos reales. "
            "Evitas cliches genéricos. Cada frase debe aportar valor."
        )

        user = f"""Genera el copy para un brochure inmobiliario de 15 slides sobre Mazatlán,
basándote EXCLUSIVAMENTE en estas estadísticas reales del mercado actual:

{json.dumps(stats, ensure_ascii=False, indent=2)}

Devuelve un JSON con esta estructura EXACTA (valores en español de México, sin emojis en texto):

{{
  "portada": {{
    "titulo": "frase emocional corta de 5-8 palabras que invite a invertir",
    "subtitulo": "subtítulo de 8-12 palabras que posicione a Mazatlán"
  }},
  "storytelling": "párrafo de 3-4 líneas narrativas sobre la transformación de Mazatlán; menciona el dato de que hemos analizado {resumen['total_propiedades']} propiedades",
  "razones": {{
    "lista": ["razón 1 corta", "razón 2 corta", "razón 3 corta", "razón 4 corta"],
    "frase_clave": "cita aspiracional de una línea sobre plusvalía futura"
  }},
  "tendencias": ["tendencia 1", "tendencia 2", "tendencia 3", "tendencia 4"],
  "riesgos": ["riesgo 1", "riesgo 2"],
  "oportunidades": ["oportunidad 1", "oportunidad 2"]
}}

Cada ítem en las listas debe ser corto (4-8 palabras máximo), directo, sin cliches."""

        result = self._invoke_json(system, user)

        # Merge con fallbacks si algo faltó
        out = {
            "portada": result.get("portada", FALLBACK_COPY["portada"]) if result else FALLBACK_COPY["portada"],
            "storytelling": result.get("storytelling", FALLBACK_COPY["storytelling"]) if result else FALLBACK_COPY["storytelling"],
            "razones": result.get("razones", FALLBACK_COPY["razones"]) if result else FALLBACK_COPY["razones"],
            "tendencias": result.get("tendencias", FALLBACK_COPY["tendencias"]) if result else FALLBACK_COPY["tendencias"],
            "riesgos": result.get("riesgos", FALLBACK_COPY["riesgos"]) if result else FALLBACK_COPY["riesgos"],
            "oportunidades": result.get("oportunidades", FALLBACK_COPY["oportunidades"]) if result else FALLBACK_COPY["oportunidades"],
        }

        return out


if __name__ == "__main__":
    # Debug: python -m brochure.llm_writer
    from brochure.analyzer import analizar_mercado

    datos = analizar_mercado()
    writer = BrochureLLMWriter()
    copy = writer.generar_todo(datos)
    print(json.dumps(copy, ensure_ascii=False, indent=2))
