# Lokální backend

Malý Flask backend pro lokální přihlašování proti PostgreSQL.

## Spuštění

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
- `GET /api/auth/me`
- `POST /api/auth/logout`
- `GET /api/approver/dashboard`

## Lokální účet

Seed vytváří účet `admin@local` a login `admin`.
