# Databáze cestovních příkazů

Lokální PostgreSQL databáze pro autonomní verzi aplikace.

## Databáze

- Databáze: `travel_orders`
- Schéma: `travel`
- Hlavní migrace: `database/migrations/001_schema.sql`

## Hlavní oblasti

- lokální uživatelé a role,
- budoucí mapování uživatelů a zaměstnanců na Helios,
- zaměstnanecké profily, střediska, útvary a projekty,
- cestovní příkazy, řádky vyúčtování, přílohy a výpočtové snapshoty,
- schvalovací pravidla a konkrétní schvalovací požadavky,
- upozornění pro schvalovatele a uživatele,
- auditní log,
- fronta a mapování pro budoucí synchronizaci/export do Heliosu.

## Lokální administrátor

Seed vytváří uživatele `admin@local` / `admin`. Heslo se předává při spuštění seedu jako proměnná `app_admin_password`.

## Dashboardy

Pohledy:

- `travel.v_approver_pending_orders`
- `travel.v_approver_dashboard`
- `travel.v_user_notification_badge`

## Další migrace

Migrace `006_registration_and_erp_sync.sql` doplňuje samoobslužnou registraci:

- `travel.app_user.email_verified_at`,
- `travel.email_verification_token`.
