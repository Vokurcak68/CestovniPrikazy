# Lokální backend

Malý Flask backend pro lokální přihlašování proti PostgreSQL.

## Spuštění

Volitelně zkopírujte kořenový `.env.example` do `.env` a doplňte lokální hodnoty pro PostgreSQL, ERP Helios a SMTP.

```powershell
.\travel-orders-server\start-local.ps1
```

Backend poběží na:

```text
http://127.0.0.1:5055
```

Při spuštění se zeptá na heslo k PostgreSQL. Heslo se nastaví jen do proměnné prostředí běžícího procesu.

## Endpointy

- `POST /api/auth/login`
- `POST /api/auth/register`
- `GET /api/auth/verify-email`
- `GET /api/auth/me`
- `POST /api/auth/logout`
- `POST /api/users/me/erp-sync`
- `GET /api/approver/dashboard`

## Helios ERP

Synchronizace profilu používá `sqlcmd` a proměnné prostředí:

- `ERP_DB_SERVER`
- `ERP_DB_NAME`
- `ERP_DB_USER`
- `ERP_DB_PASSWORD`
- `ERP_DB_ENCRYPT`
- `ERP_USERS_VIEW`
- `ERP_VEHICLES_VIEW`
- `HELIOS_IMPORT_API_TOKEN` pro cteni importnich kandidatu z Heliosu pres hlavicku `X-Helios-Import-Token`

Endpoint `POST /api/users/me/erp-sync` načte zaměstnance z `ERP_USERS_VIEW` přes `Cislo` a auta z `ERP_VEHICLES_VIEW` přes `CisloRidic`. Hesla patří pouze do lokálního `.env`, ne do repozitáře.

Endpoint `GET /api/helios/import-candidates` je pro Helios dostupny bud prihlasenemu adminovi/ucetni, nebo servisne pres token:

```http
X-Helios-Import-Token: hodnota-z-HELIOS_IMPORT_API_TOKEN
```

Po uspesnem zalozeni hlavicky v `dbo.TabICestak` zavola Helios callback:

```http
POST /api/helios/import-results
X-Helios-Import-Token: hodnota-z-HELIOS_IMPORT_API_TOKEN
Content-Type: application/json

{
  "importId": "uuid-z-import-candidates",
  "orderNo": "CP-2026-0001",
  "project": { "code": "123456" }
}
```

`project.code` je ID zalozeneho cestaku v Heliosu (`TabICestak.id`). Aplikace ho ulozi do `travel_order.helios_document_id`, prepne `export_status` na `exported` a dalsi vyber importu ho uz nevrati.

## Registrace a e-mail

Registrace vytvoří neaktivní účet a token pro ověření e-mailu. Pokud nejsou nastavené `SMTP_*` proměnné, běží lokální vývojový režim `EMAIL_DEV_MODE=true` a API vrátí ověřovací odkaz v odpovědi.

## Lokální účet

Seed vytváří účet `admin@local` a login `admin`.
