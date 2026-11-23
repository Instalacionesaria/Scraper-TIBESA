"""
Carga y limpieza de TODAS las propiedades guardadas para el Analista de Mercado.

Lee la tabla `tibesa_web_propiedades` de Supabase (todos los portales) y convierte
el payload heterogéneo de cada scraper en un registro uniforme y comparable:

- precio total en MXN (USD convertido con TIPO_CAMBIO_USD_MXN)
- operación (venta / renta) y tipo de propiedad normalizado
- superficie y precio por m²
- ciudad y zona/colonia extraídas del texto de ubicación
- marca de duplicado cuando el mismo anuncio aparece en varios portales
- marca de precio no válido (p. ej. "$1", o un precio por m² publicado como total)

El resultado se cachea en memoria unos minutos: los datos solo cambian cuando
alguien re-scrapea un portal.
"""

import os
import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

from leads.supabase_client import SUPABASE_KEY, SUPABASE_URL


TABLA = "tibesa_web_propiedades"
PAGINA_LECTURA = 1000
CACHE_SEGUNDOS = 3600  # además se invalida al guardar un scrapeo nuevo (invalidar_cache)
TIPO_CAMBIO_USD_MXN = float(os.getenv("TIPO_CAMBIO_USD_MXN", "18.5"))
GRAN_EXTENSION_M2 = 10000  # 1 hectárea: a partir de aquí es terreno rústico/desarrollo, otro mercado

# Portales que republican anuncios de otros: si hay duplicado, se prefiere el original.
AGREGADORES = {"mitula", "trovit", "icasas"}

NOMBRE_PORTAL = {
    "paraiso_dorado": "Paraíso Dorado", "lamudi": "Lamudi", "mitula": "Mitula",
    "remax_sunset_eagle": "RE/MAX", "pincali": "Pincali", "propiedades_com": "Propiedades.com",
    "casasyterrenos": "Casas y Terrenos", "century21": "Century 21", "depreventa": "DePreventa",
    "trovit": "Trovit", "mazatlan_br": "Mazatlán Bienes Raíces", "mazatlan_bienes_raices": "Mazatlán Bienes Raíces",
    "icasas": "iCasas", "spezia": "Spezia", "realtor": "Realtor.com", "buscatucasa": "BuscaTuCasa",
    "doorvel": "Doorvel", "palmaz": "Palmaz", "nocnok": "NocNok", "kwmexico": "KW México",
}

TIPOS = {
    "terreno": ["terreno", "lote", "predio", "hectarea", "rancho", "agricola", "vacante"],
    "casa": ["casa", "residencia"],
    "departamento": ["departamento", "condominio", "depto", "penthouse", "loft", "suite", "torre"],
    "comercial": ["local", "comercial", "plaza", "bodega", "oficina", "edificio", "nave", "industrial", "hotel"],
}

# Partes de la ubicación que no son una zona/colonia.
_NO_ZONA = {
    "sinaloa", "sin", "sin.", "mexico", "méxico", "mx", "mazatlan", "mazatlán", "municipio de mazatlan",
    "mazatlan sinaloa", "mazatlán sinaloa", "ciudad de mazatlan", "mazatlan, sinaloa",
}
_PREFIJOS_ZONA = re.compile(
    r"^(fraccionamiento|fracc\.?|colonia|col\.?|residencial|privada|condominio|desarrollo|zona)\s+", re.I
)
_TIPO_EN = re.compile(r"^(terreno|lote|casa|departamento|local|bodega|oficina|condominio)s?\s+en\s+", re.I)

# Variantes de una misma zona que conviene agrupar.
_ALIAS_ZONA = {
    "marina": "Marina Mazatlán",
    "marina mazatlan": "Marina Mazatlán",
    "zona dorada / sabalo": "Zona Dorada",
    "zona dorada": "Zona Dorada",
    "dorada": "Zona Dorada",
    "cerritos resort": "Cerritos",
    "cerritos": "Cerritos",
    "centro historico": "Centro Histórico",
    "centro": "Centro",
    "el cid": "El Cid",
    "cid": "El Cid",
    "este mazatlan": "Este Mazatlán",
    "nuevo mazatlan": "Nuevo Mazatlán",
    "mazatlan centro": "Centro",
    "venadillo": "El Venadillo",
}


def sin_acentos(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in texto if unicodedata.category(c) != "Mn").lower().strip()


@dataclass
class Propiedad:
    id: str
    portal: str
    titulo: str
    url: Optional[str]
    tipo: str
    tipo_original: Optional[str]
    operacion: str
    precio_texto: Optional[str]
    moneda: str
    precio_mxn: Optional[float]          # precio total en MXN (None si no hay o no es válido)
    precio_m2: Optional[float]           # MXN por m² de superficie
    superficie_m2: Optional[float]
    construccion_m2: Optional[float]
    recamaras: Optional[int]
    banos: Optional[float]
    ciudad: str
    zona: str
    ubicacion: str
    actualizado: Optional[str]
    precio_valido: bool = True
    nota_precio: Optional[str] = None
    duplicado: bool = False
    gran_extension: bool = False
    tambien_en: List[str] = field(default_factory=list)

    @property
    def texto_busqueda(self) -> str:
        return sin_acentos(f"{self.titulo} {self.zona} {self.ubicacion}")


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------

# Solo los campos del payload que usa el análisis (sin descripciones largas ni imágenes):
# reduce mucho lo que se descarga de Supabase (egress).
CAMPOS_DATOS = [
    "titulo", "precio", "precio_normalizado", "precio_numerico", "moneda", "tipo_propiedad",
    "tipo_operacion", "estado", "url", "ubicacion", "zona", "terreno", "property_id", "site",
]
CAMPOS_ANALISIS = ["terreno", "construccion", "tipo_propiedad"]
CAMPOS_CARACTERISTICAS = ["superficie_m2", "construccion_m2", "recamaras", "banos"]


def _select() -> str:
    partes = ["fuente", "property_id", "scraped_at"]
    partes += [f"d_{c}:datos->{c}" for c in CAMPOS_DATOS]
    partes += [f"a_{c}:datos->analisis_llm->{c}" for c in CAMPOS_ANALISIS]
    partes += [f"c_{c}:datos->caracteristicas->{c}" for c in CAMPOS_CARACTERISTICAS]
    return ",".join(partes)


def _armar_fila(row: Dict[str, Any]) -> Dict[str, Any]:
    """Reconstruye la forma {fuente, property_id, scraped_at, datos:{...}} que espera normalizar()."""
    datos = {c: row.get(f"d_{c}") for c in CAMPOS_DATOS}
    datos["analisis_llm"] = {c: row.get(f"a_{c}") for c in CAMPOS_ANALISIS}
    datos["caracteristicas"] = {c: row.get(f"c_{c}") for c in CAMPOS_CARACTERISTICAS}
    return {"fuente": row.get("fuente"), "property_id": row.get("property_id"),
            "scraped_at": row.get("scraped_at"), "datos": datos}


def _leer_filas() -> List[Dict[str, Any]]:
    headers = {"apikey": SUPABASE_KEY or "", "Authorization": f"Bearer {SUPABASE_KEY or ''}"}
    base = f"{SUPABASE_URL}/rest/v1/{TABLA}?select={_select()}&order=fuente.asc,property_id.asc"
    filas: List[Dict[str, Any]] = []
    while True:
        r = requests.get(f"{base}&limit={PAGINA_LECTURA}&offset={len(filas)}", headers=headers, timeout=30)
        r.raise_for_status()
        pagina = r.json()
        filas.extend(pagina)
        if len(pagina) < PAGINA_LECTURA:
            return [_armar_fila(f) for f in filas]


# ---------------------------------------------------------------------------
# Normalización
# ---------------------------------------------------------------------------

def _numero(valor: Any) -> Optional[float]:
    if isinstance(valor, (int, float)):
        return float(valor) if valor > 0 else None
    if isinstance(valor, str):
        digitos = re.sub(r"[^\d.]", "", valor.replace(",", ""))
        try:
            n = float(digitos) if digitos else None
        except ValueError:
            return None
        return n if n and n > 0 else None
    return None


def _precio(d: Dict[str, Any]) -> tuple[Optional[float], str]:
    pn = d.get("precio_normalizado") if isinstance(d.get("precio_normalizado"), dict) else {}
    texto = str(d.get("precio") or "")
    numero = _numero(pn.get("precio_numerico")) or _numero(d.get("precio_numerico")) or _numero(texto)
    moneda = (d.get("moneda") or pn.get("moneda") or "").upper()
    if "USD" in texto.upper() or "US$" in texto.upper():
        moneda = "USD"
    if moneda not in ("MXN", "USD"):
        moneda = "MXN"
    return numero, moneda


def _tipo(d: Dict[str, Any]) -> str:
    analisis = d.get("analisis_llm") if isinstance(d.get("analisis_llm"), dict) else {}
    original = sin_acentos(str(d.get("tipo_propiedad") or analisis.get("tipo_propiedad") or ""))
    for texto in (original, sin_acentos(str(d.get("titulo") or ""))):
        for tipo, claves in TIPOS.items():
            if any(c in texto for c in claves):
                return tipo
    return "otro"


def _operacion(d: Dict[str, Any]) -> str:
    campos = " ".join(str(d.get(k) or "") for k in ("tipo_operacion", "estado"))
    titulo = sin_acentos(str(d.get("titulo") or ""))
    url = sin_acentos(str(d.get("url") or ""))
    if re.search(r"[/-](en-)?renta[/-]|/rent/|for-rent", url):
        return "renta"
    if "renta" in sin_acentos(campos) or re.search(r"\b(en renta|renta vacacional|se renta|rento)\b", titulo):
        return "renta"
    return "venta"


def _superficies(d: Dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
    analisis = d.get("analisis_llm") if isinstance(d.get("analisis_llm"), dict) else {}
    terreno = d.get("terreno") if isinstance(d.get("terreno"), dict) else {}
    car = d.get("caracteristicas") if isinstance(d.get("caracteristicas"), dict) else {}
    a_terreno = analisis.get("terreno") if isinstance(analisis.get("terreno"), dict) else {}
    a_constr = analisis.get("construccion") if isinstance(analisis.get("construccion"), dict) else {}

    sup = (_numero(terreno.get("superficie_m2")) or _numero(car.get("superficie_m2"))
           or _numero(a_terreno.get("metros_cuadrados")))
    if not sup and _numero(a_terreno.get("hectareas")):
        sup = _numero(a_terreno.get("hectareas")) * 10000
    constr = _numero(a_constr.get("metros_cuadrados")) or _numero(car.get("construccion_m2"))
    return sup, constr


def _entero(valor: Any) -> Optional[int]:
    n = _numero(valor)
    return int(n) if n and n < 50 else None


def _ciudad_y_zona(d: Dict[str, Any]) -> tuple[str, str]:
    ubicacion = str(d.get("ubicacion") or "")
    zona_campo = str(d.get("zona") or "")
    texto_ciudad = sin_acentos(f"{ubicacion} {zona_campo}")
    if "mazatl" in texto_ciudad or "villa union" in texto_ciudad or "cerritos" in texto_ciudad:
        ciudad = "Mazatlán"
    else:
        ciudad = "Otra ciudad"

    for fuente in (zona_campo, ubicacion):
        partes = [_TIPO_EN.sub("", p.strip()) for p in fuente.split(",")]
        partes = [p for p in partes if p and sin_acentos(p).rstrip(".") not in _NO_ZONA and not re.fullmatch(r"[\d\s-]+", p)]
        partes = [p for p in partes if not re.match(r"(?i)^(av\.?|avenida|calle|blvd\.?|boulevard|carretera|camino)\b", p)] or partes
        if partes:
            # Formato "calle, colonia, Mazatlán" o "Sinaloa, Mazatlán, colonia": la colonia es la última parte útil.
            zona = _PREFIJOS_ZONA.sub("", partes[-1]).strip(" .")
            clave = sin_acentos(zona)
            zona = _ALIAS_ZONA.get(clave, zona)
            if zona.isupper() or zona.islower():
                zona = zona.title()
            return ciudad, zona
    return ciudad, "Sin zona especificada"


def normalizar(fila: Dict[str, Any]) -> Optional[Propiedad]:
    d = fila.get("datos") or {}
    if not isinstance(d, dict):
        return None
    portal = fila.get("fuente") or d.get("site") or "?"
    numero, moneda = _precio(d)
    tipo = _tipo(d)
    operacion = _operacion(d)
    sup, constr = _superficies(d)
    car = d.get("caracteristicas") if isinstance(d.get("caracteristicas"), dict) else {}
    ciudad, zona = _ciudad_y_zona(d)

    precio_mxn = numero * TIPO_CAMBIO_USD_MXN if numero and moneda == "USD" else numero
    precio_m2 = None
    valido, nota = True, None

    if not precio_mxn:
        valido, nota = False, "sin precio publicado"
    elif precio_mxn < 50:
        valido, nota = False, "precio simbólico (p. ej. $1)"
    elif operacion == "venta" and tipo == "terreno" and precio_mxn < 20000:
        # El portal publicó el precio por m², no el total.
        precio_m2 = precio_mxn
        precio_mxn = precio_mxn * sup if sup else None
        nota = "el portal publica el precio por m²"
    elif operacion == "venta" and tipo != "terreno" and precio_mxn < 150000:
        valido, nota = False, "precio demasiado bajo para venta (posible renta o error)"
    elif operacion == "renta" and precio_mxn > 500000:
        valido, nota = False, "precio demasiado alto para renta"

    if valido and precio_m2 is None and precio_mxn and sup and sup >= 20:
        precio_m2 = precio_mxn / sup

    return Propiedad(
        id=str(fila.get("property_id") or d.get("property_id") or d.get("url") or ""),
        portal=portal,
        titulo=str(d.get("titulo") or "").strip() or "(sin título)",
        url=d.get("url"),
        tipo=tipo,
        tipo_original=d.get("tipo_propiedad"),
        operacion=operacion,
        precio_texto=d.get("precio"),
        moneda=moneda,
        precio_mxn=round(precio_mxn) if valido and precio_mxn else None,
        precio_m2=round(precio_m2) if valido and precio_m2 else None,
        superficie_m2=sup,
        construccion_m2=constr,
        recamaras=_entero(car.get("recamaras")),
        banos=_numero(car.get("banos")),
        ciudad=ciudad,
        zona=zona,
        ubicacion=str(d.get("ubicacion") or ""),
        actualizado=fila.get("scraped_at"),
        precio_valido=valido,
        nota_precio=nota,
        gran_extension=bool(sup and sup >= GRAN_EXTENSION_M2),
    )


def _marcar_duplicados(props: List[Propiedad]) -> None:
    """Mismo tipo + mismo precio + misma superficie en portales DISTINTOS = mismo anuncio."""
    grupos: Dict[tuple, List[Propiedad]] = {}
    for p in props:
        if p.precio_mxn and p.superficie_m2:
            clave = (p.tipo, p.operacion, round(p.precio_mxn, -3), round(p.superficie_m2))
            grupos.setdefault(clave, []).append(p)
    for grupo in grupos.values():
        portales = {p.portal for p in grupo}
        if len(portales) < 2:
            continue  # dentro de un mismo portal pueden ser unidades distintas de un desarrollo
        grupo.sort(key=lambda p: (p.portal in AGREGADORES, p.portal))
        principal = grupo[0]
        vistos = {principal.portal}
        for p in grupo[1:]:
            if p.portal in vistos:
                continue
            vistos.add(p.portal)
            p.duplicado = True
            principal.tambien_en.append(NOMBRE_PORTAL.get(p.portal, p.portal))


def _unificar_zonas(props: List[Propiedad]) -> None:
    """'Real del Valle' y 'Real Del Valle' son la misma zona: se usa la escritura más común."""
    conteo: Dict[str, Dict[str, int]] = {}
    for p in props:
        variantes = conteo.setdefault(sin_acentos(p.zona), {})
        variantes[p.zona] = variantes.get(p.zona, 0) + 1
    canonica = {clave: max(v, key=v.get) for clave, v in conteo.items()}
    for p in props:
        p.zona = canonica[sin_acentos(p.zona)]


# ---------------------------------------------------------------------------
# Caché
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_cache: Dict[str, Any] = {"props": None, "cargado": 0.0}


def invalidar_cache() -> None:
    """Se llama al guardar un scrapeo nuevo para que el analista vea los datos frescos."""
    with _lock:
        _cache.update(props=None, cargado=0.0)


def obtener_inventario(forzar: bool = False) -> List[Propiedad]:
    """Todas las propiedades normalizadas (cacheadas CACHE_SEGUNDOS)."""
    with _lock:
        if not forzar and _cache["props"] is not None and time.time() - _cache["cargado"] < CACHE_SEGUNDOS:
            return _cache["props"]
        props = [p for p in (normalizar(f) for f in _leer_filas()) if p]
        _unificar_zonas(props)
        _marcar_duplicados(props)
        _cache.update(props=props, cargado=time.time())
        return props
