# Request enviado al CRM de TIBESA

```
POST https://api.bienesraicestibesa.mx/contacts/createContact
Authorization: <TOKEN_JWT>
Content-Type: multipart/form-data
```

## Campos enviados

| Campo | Valor |
|---|---|
| `name` | Prueba ARIA IA |
| `email` | prueba+1777067977@tibesa-test.com |
| `source` | ariaIA |
| `phone` | +52 55 0000 0000 |
| `cellPhone` | +52 55 0000 0001 |
| `city` | Mazatlán |
| `company` | Test Company |
| `companyRol` | Gerente |
| `address` | Av. Test 123, Mazatlán, Sinaloa |
| `interests` | Bienes Raíces |
| `tag` | PRUEBA-TOKEN |

## Respuesta

```
HTTP 200
{"status":200,"results":2090}
```
