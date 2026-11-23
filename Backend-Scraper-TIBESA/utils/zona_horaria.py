"""
Zona horaria de Mazatlán para fechas visibles al cliente.

La imagen Docker del servidor (Playwright/Ubuntu) no trae la base de zonas
horarias del sistema; por eso requirements.txt incluye `tzdata`. Si aun así no
estuviera disponible, se usa UTC-7 fijo: Mazatlán (Sinaloa) no tiene horario
de verano desde 2022, así que el resultado es el mismo.
"""

from datetime import datetime, timedelta, timezone, tzinfo

try:
    from zoneinfo import ZoneInfo

    TZ_MAZATLAN: tzinfo = ZoneInfo("America/Mazatlan")
except Exception:  # ZoneInfoNotFoundError / sin base de zonas horarias
    TZ_MAZATLAN = timezone(timedelta(hours=-7), "America/Mazatlan")


def ahora_mazatlan() -> datetime:
    return datetime.now(TZ_MAZATLAN)
