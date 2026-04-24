"""Modelos Pydantic de request/response para el módulo de leads."""

import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------- Auth ----------

class LoginRequest(BaseModel):
    correo_electronico: str
    password: str


# ---------- Google Places ----------

class GooglePlacesRequest(BaseModel):
    businessType: str
    location: str
    getEmails: bool
    timestamp: datetime.datetime
    userId: str
    correo_electronico: str
    password: str


# ---------- Facebook Ads ----------

class FacebookAdsRequest(BaseModel):
    url: str
    userId: Optional[str] = None
    correo_electronico: str
    timestamp: Optional[str] = None
    # Alias por compatibilidad
    scrape_url: Optional[str] = None
    link: Optional[str] = None

    def get_url(self) -> str:
        return self.url or self.scrape_url or self.link or ""


# ---------- Facebook Pages ----------

class FacebookPageItem(BaseModel):
    page_name: Optional[str] = None
    page_profile_uri: Optional[str] = None
    page_id: Optional[str] = None


class FacebookPagesRequest(BaseModel):
    pages: List[FacebookPageItem]
    userId: Optional[str] = None
    correo_electronico: str
    timestamp: Optional[str] = None

    def get_page_urls(self) -> List[str]:
        return [p.page_profile_uri for p in self.pages if p.page_profile_uri]

    def get_original_pages_data(self) -> List[dict]:
        return [p.model_dump() for p in self.pages]


# ---------- Webhooks de Apify ----------

class ApifyWebhookResource(BaseModel):
    defaultDatasetId: str


class ApifyWebhookPayload(BaseModel):
    job_id: str
    resource: ApifyWebhookResource


# ---------- CRM TIBESA ----------

class EnviarCRMRequest(BaseModel):
    job_id: str
    etiqueta: str = Field(..., max_length=30, min_length=1)
    correo_electronico: str


# ---------- Sistema de Leads (n8n) ----------

class EnviarSistemaLeadsRequest(BaseModel):
    job_id: str
    correo_electronico: str
