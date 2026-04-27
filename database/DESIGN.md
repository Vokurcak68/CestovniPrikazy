# Návrh databázové struktury

## Princip

Databáze je navržená tak, aby autonomní aplikace mohla fungovat sama, ale později přijala údaje z Heliosu bez přepisování domény.

Z toho důvodu jsou oddělené:

- aplikační uživatelé,
- lokální autentizace,
- zaměstnanecký profil,
- číselníky synchronizované z Heliosu,
- cestovní příkazy,
- workflow schvalování,
- upozornění,
- audit,
- Helios sync/export vrstva.

## Uživatel vs zaměstnanec

`travel.app_user` je účet v aplikaci. Může být lokální, synchronizovaný z Heliosu, nebo smíšený.

`travel.employee_profile` je zaměstnanecká karta: osobní číslo, středisko, pracovní doba, defaultní schvalovatel, manažer, účetní, Helios ID a poslední synchronizovaný payload.

Toto oddělení je důležité, protože uživatel může existovat dřív než zaměstnanecký záznam z Heliosu, nebo naopak Helios může dodat zaměstnance, který zatím nemá lokální přístup.

## Přihlášení

Lokální hesla jsou v `travel.local_auth_identity`. Heslo se ukládá přes PostgreSQL `pgcrypto` a `crypt(...)`, ne v otevřeném textu.

Session tokeny jsou v `travel.auth_session` uložené jen jako SHA-256 hash. Backend uživateli vrací pouze surový token při přihlášení.

## Budoucí Helios synchronizace

Každá synchronizovatelná entita má pole typu:

- `helios_id`,
- `helios_checksum`,
- `last_synced_at`,
- případně `helios_payload`.

Obecná mapa vazeb je v `travel.helios_entity_map`. Běhy synchronizace jsou v `travel.helios_sync_run`.

To umožní synchronizovat:

- uživatele,
- zaměstnance,
- střediska,
- útvary,
- projekty/zakázky,
- vozidla.

## Schvalování

Schvalování je dvouvrstvé:

- `travel.approval_rule` a `travel.approval_rule_step` popisují pravidla,
- `travel.approval_request` jsou konkrétní úkoly pro konkrétní schvalovatele.

Schvalovatel může být pevně daný uživatel, role, nebo osoba odvozená ze zaměstnance: manažer, výchozí schvalovatel, účetní.

Dashboard používá pohledy:

- `travel.v_approver_pending_orders`,
- `travel.v_approver_dashboard`.

## Upozornění

`travel.notification` je obecná tabulka pro in-app upozornění, e-mail a později webhook. Pro MVP stačí in-app položky, později může worker posílat e-maily.

## Výpočty

Výsledky výpočtů jsou uložené ve:

- `travel.travel_route_line`,
- `travel.travel_order_total`.

`travel.travel_order_total.calculation_snapshot` slouží k auditu: při pozdější změně sazeb zůstane dohledatelné, podle čeho byla konkrétní cesta vypočtena.

## Export do Heliosu

Export je oddělený přes `travel.helios_export_queue`. Cestovní příkaz se nejdřív uzavře a připraví payload. Teprve exportní worker ho odešle do Heliosu a uloží `helios_document_id`.
