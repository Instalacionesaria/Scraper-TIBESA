"""
Prueba directa del endpoint del CRM de TIBESA para confirmar si el token actual funciona.

Uso:
    cd Backend-Scraper-TIBESA
    python test_crm_token.py
"""

import base64
import datetime
import json
import os

import requests
from dotenv import load_dotenv


load_dotenv()

CRM_API_URL = "https://api.bienesraicestibesa.mx/contacts/createContact"
CRM_API_TOKEN = os.getenv("CRM_TIBESA_API_TOKEN")


def decode_jwt_payload(token: str) -> dict:
    """Decodifica el payload de un JWT (sin validar firma)."""
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def main() -> None:
    print("=" * 70)
    print("PRUEBA DEL TOKEN DEL CRM DE TIBESA")
    print("=" * 70)

    if not CRM_API_TOKEN:
        print("❌ CRM_TIBESA_API_TOKEN no está en .env")
        return

    print(f"\nEndpoint: {CRM_API_URL}")
    print(f"Token (primeros 40 chars): {CRM_API_TOKEN[:40]}...")

    # Decodificar JWT informativo
    try:
        payload = decode_jwt_payload(CRM_API_TOKEN)
        print("\n📋 Payload JWT:", payload)
        if "exp" in payload:
            exp = datetime.datetime.fromtimestamp(payload["exp"])
            now = datetime.datetime.now()
            print(f"   Expira:     {exp}")
            print(f"   Ahora:      {now}")
            print(f"   Expirado?:  {now > exp}")
    except Exception as e:
        print(f"⚠️ No se pudo decodificar el JWT: {e}")

    # Lead de prueba con el schema actualizado del CRM
    lead = {
        # Requeridos
        "name": "Prueba ARIA IA",
        "email": f"prueba+{int(datetime.datetime.now().timestamp())}@tibesa-test.com",
        # Fijo
        "source": "ariaIA",
        # Opcionales aceptados por el CRM
        "phone": "+52 55 0000 0000",
        "cellPhone": "+52 55 0000 0001",
        "city": "Mazatlán",
        "company": "Test Company",
        "companyRol": "Gerente",
        "address": "Av. Test 123, Mazatlán, Sinaloa",
        "interests": "Bienes Raíces",
        "tag": "PRUEBA-TOKEN",
    }
    files_data = {k: (None, str(v)) for k, v in lead.items()}

    print("\n📤 Enviando lead de prueba...")
    print(f"   Body: {lead}")

    try:
        r = requests.post(
            CRM_API_URL,
            files=files_data,
            headers={"Authorization": CRM_API_TOKEN},
            timeout=30,
        )
    except requests.RequestException as e:
        print(f"\n❌ Error de red: {e}")
        return

    print(f"\n📥 HTTP {r.status_code} {r.reason}")
    print(f"   Headers: {dict(r.headers)}")
    print(f"\n   Body:\n{r.text}")

    print("\n" + "=" * 70)
    if r.status_code in (200, 201):
        print("✅ TOKEN VÁLIDO — el lead se creó en el CRM.")
    elif r.status_code in (401, 403):
        print("❌ TOKEN RECHAZADO — 401/403 (expirado o sin permisos).")
    else:
        print(f"⚠️ Respuesta inesperada (HTTP {r.status_code}). Revisa el body.")
    print("=" * 70)


if __name__ == "__main__":
    main()
