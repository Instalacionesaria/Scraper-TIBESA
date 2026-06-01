"""
Módulo de Scrapers
Contiene scrapers específicos para cada sitio inmobiliario
"""

from .base_scraper import BaseScraper
from .paraiso_dorado import ParaisoDoradoScraper
from .lamudi import LamudiScraper
from .mitula import MitulaScraper
from .remax_sunset_eagle import RemaxSunsetEagleScraper

__all__ = [
    'BaseScraper',
    'ParaisoDoradoScraper',
    'LamudiScraper',
    'MitulaScraper',
    'RemaxSunsetEagleScraper',
]
