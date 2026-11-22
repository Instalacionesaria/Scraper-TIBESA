"""
Errores compartidos por los scrapers.
"""

# Códigos HTTP con los que un portal rechaza el acceso antes de servir la página
# (anti-bot, bloqueo por IP/geo, rate limit).
HTTP_BLOQUEO = (401, 403, 429)


class SitioBloqueadoError(Exception):
    """El portal rechaza el acceso (HTTP 401/403/429) desde nuestra IP.

    No es un fallo del scraper: el sitio no deja entrar. El flujo SSE lo convierte
    en un `done` con motivo `sitio_bloqueado`, sin tocar los datos ya guardados.
    """

    def __init__(self, sitio: str, status: int):
        self.sitio = sitio
        self.status = status
        super().__init__(f"{sitio} está bloqueando el acceso (HTTP {status})")
