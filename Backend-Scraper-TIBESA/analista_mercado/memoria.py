"""
Histórico de conversaciones del Analista de Mercado (checkpointer de LangGraph).

Las conversaciones se guardan en Postgres (Supabase) con `PostgresSaver`, dentro
del esquema propio de TIBESA (`DB_SCHEMA`, por defecto `tibesa`) para no mezclarse
con `public` ni con las tablas de otros proyectos de la base compartida de ARIA.

Por qué el esquema se fija en la CONEXIÓN y no en el rol:
la base es compartida; `ALTER ROLE postgres SET search_path = tibesa` cambiaría el
esquema por defecto de TODOS los proyectos que usan ese rol. Por eso se pasa
`options=-c search_path=tibesa` en cada conexión y, al arrancar, se verifica que
`current_schema()` sea realmente `tibesa` (un pooler en modo transacción podría
ignorar esa opción): si no lo es, NO se usa Postgres, para no crear tablas en `public`.

Requiere `SUPABASE_DB_URL` = cadena de conexión del "Session pooler" de Supabase
(puerto 5432). Sin ella se usa memoria RAM (el histórico se pierde al reiniciar).
"""

import os
import threading
from typing import Any, Dict, List, Optional

from langgraph.checkpoint.memory import InMemorySaver

from .validacion_esquema_tenant import validar_esquema


DB_URL = os.getenv("SUPABASE_DB_URL", "").strip()
DB_SCHEMA = os.getenv("DB_SCHEMA", "tibesa").strip()
TABLAS_CHECKPOINTER = ("checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations")

_lock = threading.Lock()
_estado: Dict[str, Any] = {"checkpointer": None, "pool": None, "modo": None, "detalle": None}


def _conexion_kwargs() -> Dict[str, Any]:
    return {
        "autocommit": True,
        "prepare_threshold": 0,  # compatible con el pooler de Supabase
        "options": f"-c search_path={DB_SCHEMA}",  # SIN ", public" a propósito
    }


def _crear_postgres():
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
    from langgraph.checkpoint.postgres import PostgresSaver

    v = validar_esquema(DB_SCHEMA)
    if not v.ok:
        raise ValueError(f"DB_SCHEMA inválido: {v.motivos}")

    # 1) El esquema se crea con una conexión efímera ANTES del pool (la librería no crea esquemas).
    with psycopg.connect(DB_URL, autocommit=True, prepare_threshold=0) as conn:
        conn.execute(f"create schema if not exists {DB_SCHEMA}")  # nombre validado arriba
        conn.execute(f"comment on schema {DB_SCHEMA} is 'TIBESA: histórico del Analista de Mercado (checkpointer LangGraph)'")

    pool = ConnectionPool(DB_URL, min_size=1, max_size=5, kwargs={**_conexion_kwargs(), "row_factory": dict_row}, open=True)

    # 2) Verificación: si el search_path fue ignorado, abortamos antes de crear tablas en public.
    with pool.connection() as conn:
        esquema = conn.execute("select current_schema() as s").fetchone()["s"]
    if esquema != DB_SCHEMA:
        pool.close()
        raise RuntimeError(
            f"La conexión quedó en el esquema '{esquema}' y no en '{DB_SCHEMA}'. "
            "Use la cadena del 'Session pooler' (puerto 5432), no la del modo transacción (6543)."
        )

    checkpointer = PostgresSaver(pool)
    checkpointer.setup()  # crea/migra las tablas del checkpointer dentro de DB_SCHEMA

    with pool.connection() as conn:
        filas = conn.execute(
            "select table_schema from information_schema.tables where table_name = any(%s)",
            (list(TABLAS_CHECKPOINTER),),
        ).fetchall()
    fuera = {f["table_schema"] for f in filas} - {DB_SCHEMA}
    if fuera:
        print(f"⚠️ Hay tablas del checkpointer también en {fuera} (de otro proyecto o de un intento previo).")
    return checkpointer, pool


def obtener_checkpointer():
    """Checkpointer compartido (Postgres si hay SUPABASE_DB_URL; si no, RAM)."""
    with _lock:
        if _estado["checkpointer"] is not None:
            return _estado["checkpointer"]
        if DB_URL:
            try:
                checkpointer, pool = _crear_postgres()
                _estado.update(checkpointer=checkpointer, pool=pool, modo="postgres",
                               detalle=f"Supabase, esquema {DB_SCHEMA}")
                print(f"🧠 Analista de Mercado: histórico en Postgres (esquema {DB_SCHEMA})")
                return checkpointer
            except Exception as e:
                print(f"❌ No se pudo usar Postgres para el histórico ({e}). Se usa memoria RAM.")
                _estado["detalle"] = f"RAM (error Postgres: {e})"
        else:
            print("⚠️ SUPABASE_DB_URL no configurada: el histórico del Analista vive en RAM y se pierde al reiniciar.")
            _estado["detalle"] = "RAM (falta SUPABASE_DB_URL)"
        _estado.update(checkpointer=InMemorySaver(), modo="memoria")
        return _estado["checkpointer"]


def estado_memoria() -> Dict[str, Optional[str]]:
    obtener_checkpointer()
    return {"modo": _estado["modo"], "detalle": _estado["detalle"]}


def listar_hilos(usuario: str, limite: int = 30) -> List[Dict[str, Any]]:
    """thread_id + fecha del último checkpoint de cada conversación del usuario (más reciente primero)."""
    checkpointer = obtener_checkpointer()
    vistos: Dict[str, Dict[str, Any]] = {}
    for tupla in checkpointer.list(None, filter={"usuario": usuario}, limit=5000):
        cfg = tupla.config.get("configurable", {})
        tid = cfg.get("thread_id")
        if not tid or cfg.get("checkpoint_ns"):
            continue
        ts = tupla.checkpoint.get("ts")
        if tid not in vistos or (ts and ts > vistos[tid]["actualizado"]):
            vistos[tid] = {"thread_id": tid, "actualizado": ts}
    hilos = sorted(vistos.values(), key=lambda h: h["actualizado"] or "", reverse=True)
    return hilos[:limite]


def dueno_del_hilo(thread_id: str) -> Optional[str]:
    tupla = obtener_checkpointer().get_tuple({"configurable": {"thread_id": thread_id}})
    return (tupla.metadata or {}).get("usuario") if tupla else None


def borrar_hilo(thread_id: str) -> None:
    obtener_checkpointer().delete_thread(thread_id)
