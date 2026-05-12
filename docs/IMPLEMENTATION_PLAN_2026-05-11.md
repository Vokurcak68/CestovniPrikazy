# Implementacni plan: Zadosti o cestovni prikaz + dvoustupnove schvalovani

## Cile
- Zavest povinnou entitu "zadost o vycestovani".
- Zakazat zalozeni cestovniho prikazu bez schvalene zadosti.
- Zmenit schvalovani cestovnich prikazu na:
  - 1. krok: ucetni (schvalit / vratit k doplneni)
  - 2. krok: schvalovatel autora (finalni schvaleni/zamitnuti)
- Posilat emaily pri vsech presunech stavu.
- Dodat MSSQL select schvalenych zadosti bez navazaneho cestaku.

## Faze 1 - Datovy model (DB)
1. Nova tabulka `travel.travel_request`.
2. Nove enumy:
   - `travel.request_status` (`draft`, `submitted`, `approved`, `rejected`, `cancelled`)
   - `travel.approval_stage` (`request`, `accounting`, `manager`)
3. Rozsireni `travel.approval_request` o:
   - `stage travel.approval_stage`
   - `rejection_reason text`
4. Rozsireni `travel.travel_order` o:
   - `travel_request_id uuid`
   - `final_approver_user_id uuid`
   - constraint na vazbu zadosti
5. Indexy:
   - stavy zadosti + owner + approver
   - approval stage pending
   - travel_order.request_id

## Faze 2 - Backend API
1. Zadosti:
   - `POST /api/travel-requests` (ulozeni draftu)
   - `POST /api/travel-requests/<id>/submit`
   - `GET /api/travel-requests/my`
   - `GET /api/travel-requests/pending`
   - `POST /api/travel-requests/<id>/decision` (`approved`/`rejected`, u reject povinny duvod)
2. Cestovni prikaz:
   - submit musi kontrolovat schvalenou zadost
   - ulozit `travel_request_id`
   - vytvorit approval request pro ucetni stage
3. Decision endpoint pro approval:
   - accounting -> manager handoff
   - manager -> finalni stav
4. Email hooky:
   - zadost o schvaleni
   - rozhodnuti o zadosti
   - cestak ke kontrole ucetni
   - rozhodnuti ucetni
   - finalni rozhodnuti schvalovatele

## Faze 3 - Frontend
1. Novy modul "Zadosti o vycestovani":
   - seznam, detail, nova zadost, odeslani.
2. Schvalovaci pohled:
   - oddelit zadosti a cestaky (filtrem nebo taby).
3. Vytvoreni cestaku:
   - pouze ze schvalene zadosti.
   - predvyplneni cil/data/duvod.
4. Stavy a tlacitka:
   - ucetni workflow (schvalit/vratit)
   - manager workflow (schvalit/zamitnout)

## Faze 4 - Integrace a SQL
1. MSSQL select schvalenych zadosti bez cestaku.
2. Aktualizace dokumentace ERP mapovani.

## Faze 5 - Testy
1. End-to-end happy path.
2. Zamitnuti zadosti (s povinnym duvodem).
3. Blokace zalozeni cestaku bez schvalene zadosti.
4. Ucetni vraceni k doplneni.
5. Ucetni schvaleni + finalni manager schvaleni.
6. Verifikace email notifikaci.
