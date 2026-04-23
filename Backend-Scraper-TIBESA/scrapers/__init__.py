"""
Módulo de Scrapers
Contiene scrapers específicos para cada sitio inmobiliario
"""

from .base_scraper import BaseScraper
from .paraiso_dorado import ParaisoDoradoScraper

__all__ = ['BaseScraper', 'ParaisoDoradoScraper']
