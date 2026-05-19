# ERP Integrace - Helios

Dokumentace tabulek, views a procedur pro integraci aplikace Cestovní příkazy s ERP systémem Helios.

---

## 1. IMPORT DAT Z HELIOSU DO APLIKACE

Aplikace čte data z Heliosu pomocí views. Tyto views jsou konfigurovatelné přes environment proměnné.

### 1.1 Views v Heliosu (čtení DO aplikace)

| Název view | Environment proměnná | Účel | Klíčový sloupec |
|-----------|---------------------|------|-----------------|
| **`hvw_vok_Oresi_CPUzivatele`** | `ERP_USERS_VIEW` | Zaměstnanci/Uživatelé | `Cislo` (osobní číslo) |
| **`hvw_vok_Oresi_CPAuta`** | `ERP_VEHICLES_VIEW` | Vozidla | `CisloRidic` (číslo řidiče) |
| **`hvw_vok_Oresi_CPKL`** | `ERP_EXCHANGE_RATES_VIEW` | Kurzovní lístek (směnné kurzy) | - |
| **`hvw_vok_Oresi_CPCestDZ`** | `ERP_FOREIGN_COUNTRIES_VIEW` | Cestovné do zahraničí | - |
| **`hvw_vok_Oresi_CPNaklKod`** | `ERP_EXPENSE_CODES_VIEW` | Nákladové kódy | - |

### 1.2 Použité sloupce z views

#### View: `hvw_vok_Oresi_CPUzivatele` (Zaměstnanci)
- `Cislo` / `ID` - osobní číslo zaměstnance (int)
- `Jmeno` - jméno
- `Email` - e-mail
- `Organizace` - organizace
- `Stredisko` / `KodStrediska` - kód střediska
- `NazevStrediska` - název střediska
- `Utvar` - útvar/oddělení
- `Adresa` - adresa
- `Telefon` - telefon
- `ZacatekPrace` - začátek pracovní doby (time)
- `KonecPrace` - konec pracovní doby (time)

#### View: `hvw_vok_Oresi_CPAuta` (Vozidla)
- `CisloRidic` - osobní číslo řidiče (int)
- `ID` / `CisloAuta` / `Cislo` - ID vozidla v Heliosu
- `EvCislo` - evidenční číslo vozidla
- `SPZ` - registrační značka
- `Znacka` - značka vozidla (např. Škoda)
- `Model` / `Typ` - model vozidla
- `Palivo` - typ paliva (B/N/E)
- `Spotreba` - spotřeba (l/100km)
- `Sazba` / `SazbaKm` - sazba za km

---

## 2. EXPORT DAT Z APLIKACE DO HELIOSU

Aplikace zapisuje schválené cestovní příkazy do staging tabulky v databázi Heliosu. Helios pak čte z view a importuje přes stored proceduru.

### 2.1 Staging tabulka v Heliosu (zápis Z aplikace)

#### Tabulka: `dbo.vok_CPImportCestaky`

**Účel:** Staging area pro cestovní příkazy připravené k importu do Heliosu.

**Klíčové sloupce:**

| Sloupec | Typ | Popis |
|---------|-----|-------|
| `ImportId` | uniqueidentifier | **PRIMARY KEY** - GUID pro identifikaci |
| `CisloCestovnihoPrikazu` | nvarchar(20) | Číslo CP v aplikaci (např. CP-2026-0001) |
| `StavAplikace` | nvarchar(30) | Stav v aplikaci (např. 'approved') |
| `ExportStatus` | nvarchar(30) | Stav exportu: 'not_ready', 'queued', 'exported' |
| `SchvalenoDne` | datetime2(0) | Datum schválení |
| `OdeslanoDne` | datetime2(0) | Datum odeslání |
| `CisloZamestnance` | int | Osobní číslo zaměstnance |
| `OsobniCisloVAplikaci` | nvarchar(30) | Osobní číslo v aplikaci (může být text) |
| `OsobniCisloOverenoVErp` | bit | Zda bylo číslo ověřeno v ERP |
| `Zamestnanec` | nvarchar(255) | Jméno zaměstnance |
| `Email` | nvarchar(255) | E-mail |
| `Organizace` | nvarchar(255) | Organizace |
| `StrediskoZamestnance` | nvarchar(30) | Středisko zaměstnance |
| `StrediskoNazev` | nvarchar(255) | Název střediska |
| `Utvar` | nvarchar(255) | Útvar |
| `UcelCesty` | nvarchar(max) | Účel cesty |
| `CilCesty` | nvarchar(60) | Cíl cesty (zkrácený) |
| `CilCestyPlnyText` | nvarchar(255) | Cíl cesty (plný text) |
| `NavstiveneFirmy` | nvarchar(255) | Navštívené firmy |
| `Spolucestujici` | nvarchar(255) | Spolucestující |
| `DatVystDokl` | datetime2(0) | Datum vystavení dokladu |
| `DatCasPocatek` | datetime2(0) | Datum a čas začátku cesty |
| `DatCasKonec` | datetime2(0) | Datum a čas konce cesty |
| `Stredisko` | nvarchar(30) | Středisko pro účtování |
| `TypCesty` | nchar(1) | 'T' = tuzemská, 'Z' = zahraniční |
| `TypDopravy` | nchar(1) | Typ dopravy |
| `SPZ` | nvarchar(20) | SPZ vozidla |
| `KMCelkem` | decimal(19,6) | Celkem km |
| `KMZahr` | decimal(19,6) | Km v zahraničí |
| `Spotreba` | decimal(19,6) | Spotřeba (l/100km) |
| `CenaL` | decimal(19,6) | Cena za litr PHM |
| `SazbaKM` | decimal(19,6) | Sazba za km |
| `PHMKc` | decimal(19,6) | PHM v Kč |
| `CelkemPHM` | decimal(19,6) | Celkem PHM |
| `CelkemDiety` | decimal(19,6) | Celkem diety (stravné) |
| `CelkemNaklady` | decimal(19,6) | Celkem náklady (výdaje) |
| `CelkemNahrady` | decimal(19,6) | Celkem náhrady |
| `CelkemPrepocet` | decimal(19,6) | Celková částka přepočet |
| `MenaPrepocet` | nvarchar(3) | Měna přepočtu |
| `KurzPrepocet` | decimal(19,6) | Kurz přepočtu |
| `HodinCelkem` | decimal(19,6) | Celkem hodin |
| `Zaloha` | decimal(19,6) | Záloha |
| `DoplatekNeboVratka` | decimal(19,6) | Doplatek nebo vrátka |
| `DoplatekNeboVratkaZaokrouhlene` | decimal(19,6) | Doplatek/vrátka zaokrouhlené |
| `IsActive` | bit | Aktivní záznam (1) nebo smazaný (0) |
| `SyncBatchId` | uniqueidentifier | ID synchronizační dávky |
| `SyncedAt` | datetime2(0) | Datum poslední synchronizace |
| `ImportStartedAt` | datetime2(0) | Kdy začal import v Heliosu |
| `ImportFinishedAt` | datetime2(0) | Kdy skončil import v Heliosu |
| `HeliosCestakId` | int | ID cestáku v Heliosu po importu |
| `ImportError` | nvarchar(max) | Chybová zpráva při importu |
| `PayloadJson` | nvarchar(max) | Kompletní JSON payload |

**Index:**
```sql
CREATE INDEX IX_vok_CPImportCestaky_KImportu
ON dbo.vok_CPImportCestaky(IsActive, ExportStatus, SchvalenoDne DESC, CisloCestovnihoPrikazu);
```

### 2.2 Views v Heliosu (čtení Heliosem)

#### View: `dbo.vok_CPImportCestakyKImportu`

**Účel:** View pro Helios, který filtruje pouze cestáky připravené k importu.

**SELECT dotaz:**
```sql
SELECT
  ImportId,
  NahledUrl,  -- URL pro náhled CP v aplikaci
  CisloCestovnihoPrikazu,
  SchvalenoDne,
  OdeslanoDne,
  CisloZamestnance,
  OsobniCisloVAplikaci,
  OsobniCisloOverenoVErp,
  Zamestnanec,
  Email,
  Organizace,
  StrediskoZamestnance,
  StrediskoNazev,
  Utvar,
  UcelCesty,
  CilCesty,
  CilCestyPlnyText,
  NavstiveneFirmy,
  Spolucestujici,
  DatVystDokl,
  DatCasPocatek,
  DatCasKonec,
  Stredisko,
  TypCesty,
  TypDopravy,
  SPZ,
  KMCelkem,
  KMZahr,
  Spotreba,
  CenaL,
  SazbaKM,
  PHMKc,
  CelkemPHM,
  CelkemDiety,
  CelkemNaklady,
  CelkemNahrady,
  CelkemPrepocet,
  MenaPrepocet,
  KurzPrepocet,
  HodinCelkem,
  Zaloha,
  DoplatekNeboVratka,
  DoplatekNeboVratkaZaokrouhlene,
  StavAplikace,
  ExportStatus,
  SyncedAt,
  StavImportu
FROM dbo.vok_CPImportCestakyPrehled
WHERE IsActive = 1
  AND StavAplikace = 'approved'
  AND ExportStatus <> 'exported'
  AND OsobniCisloOverenoVErp = 1
  AND HeliosCestakId IS NULL;
```

**Použití v Heliosu:**
```sql
-- Helios čte připravené cestáky k importu
SELECT * FROM dbo.vok_CPImportCestakyKImportu;
```

#### View: `dbo.vok_CPImportCestakyPrehled`

**Účel:** Rozšířený pohled s náhledovým URL pro otevření cestovního příkazu v aplikaci.

Obsahuje všechny sloupce z `vok_CPImportCestaky` plus:
- `NahledUrl` - URL pro náhled CP v aplikaci (sestavené z konfigurace)

### 2.3 Stored Procedura pro import do Heliosu

#### Procedura: `dbo.vok_CPImportCestak`

**Účel:** Importuje jeden cestovní příkaz z staging tabulky do Heliosu.

**Parametry:**

| Parametr | Typ | Povinný | Default | Popis |
|----------|-----|---------|---------|-------|
| `@ImportId` | uniqueidentifier | **ANO** | - | GUID z `vok_CPImportCestaky.ImportId` |
| `@CisDok` | nvarchar(20) | **ANO** | NULL | Číslo dokladu v Heliosu (např. 'CPR-000123') |
| `@DryRun` | bit | NE | 1 | `1` = test s ROLLBACK, `0` = skutečný import |
| `@ApiUrl` | nvarchar(4000) | NE | NULL | URL API pro callback (nebo z konfigurace) |
| `@ApiToken` | nvarchar(4000) | NE | NULL | API token pro callback (nebo z konfigurace) |

**Použití:**

##### Test run (dry run):
```sql
EXEC dbo.vok_CPImportCestak
  @ImportId = '7804C9B7-1FEC-4D6E-B6C5-47B6DB224B08',
  @CisDok = N'CPR-000123',
  @DryRun = 1;
```

##### Skutečný import:
```sql
EXEC dbo.vok_CPImportCestak
  @ImportId = '7804C9B7-1FEC-4D6E-B6C5-47B6DB224B08',
  @CisDok = N'CPR-000123',
  @DryRun = 0;
```

**Co procedura dělá:**

1. **Načte data** z tabulky `vok_CPImportCestaky` podle `@ImportId`
2. **Vytvoří zakázku** v tabulce `TabIZakazky` (pokud ještě neexistuje)
   - `Rada` = 'CPR'
   - `CisloZakazky` = číslo CP
   - `Nazev` = účel cesty
3. **Vytvoří nebo najde vozidlo** v tabulce `TabIVozidla`
   - Hledá podle SPZ
   - Pokud neexistuje, vytvoří nové
4. **Vytvoří cestovní příkaz** v tabulce `TabICestak` s číslem `@CisDok`
   - Vyplní všechny údaje z payloadu
   - Propojí se zakázkou a vozidlem
5. **Vytvoří řádky cestáku** (trasy, výdaje, diety, nocležné)
6. **Zavolá callback API** do aplikace s výsledkem importu
   - URL: z parametru `@ApiUrl` nebo z konfigurace
   - Body: JSON s výsledkem (úspěch/chyba)
7. **Aktualizuje staging tabulku**
   - Nastaví `HeliosCestakId` = ID z Heliosu
   - Nastaví `ImportFinishedAt` = aktuální čas
   - Nastaví `ExportStatus` = 'exported' (v případě úspěchu)

**Helios tabulky, do kterých procedura zapisuje:**
- `TabIZakazky` - zakázky
- `TabIVozidla` - vozidla
- `TabICestak` - hlavičky cestovních příkazů
- `TabICestakRadky` - řádky cestovních příkazů

### 2.4 Konfigurační tabulka

#### Tabulka: `dbo.vok_CPImportNastaveni`

**Účel:** Konfigurace pro integraci (klíč-hodnota).

**Struktura:**
| Sloupec | Typ | Popis |
|---------|-----|-------|
| `Klic` | nvarchar(100) | **PRIMARY KEY** - Klíč konfigurace |
| `Hodnota` | nvarchar(max) | Hodnota |
| `Popis` | nvarchar(255) | Popis konfigurace |
| `UpdatedAt` | datetime2(0) | Datum poslední změny |

**Klíče konfigurace:**

| Klíč | Popis | Příklad hodnoty |
|------|-------|-----------------|
| `ImportResultsApiUrl` | URL pro callback po importu | `http://127.0.0.1:5055/api/helios/import-callback` |
| `ImportApiToken` | Token pro autentizaci callbacku | `secret-token-123` |
| `TravelOrderPreviewUrl` | URL base pro náhled CP | `http://192.168.0.54:5055/helios/preview` |

**Nastavení konfigurace:**
```sql
-- Nastavení URL pro callback
INSERT INTO dbo.vok_CPImportNastaveni (Klic, Hodnota, Popis)
VALUES (
  N'ImportResultsApiUrl',
  N'http://127.0.0.1:5055/api/helios/import-callback',
  N'URL pro zaslání výsledku importu zpět do aplikace'
);

-- Nastavení tokenu
INSERT INTO dbo.vok_CPImportNastaveni (Klic, Hodnota, Popis)
VALUES (
  N'ImportApiToken',
  N'your-secret-token-here',
  N'Token pro autentizaci callback požadavků'
);

-- Nastavení URL pro náhled
INSERT INTO dbo.vok_CPImportNastaveni (Klic, Hodnota, Popis)
VALUES (
  N'TravelOrderPreviewUrl',
  N'http://192.168.0.54:5055/helios/preview',
  N'Base URL pro zobrazení náhledu cestovního příkazu'
);
```

---

## 3. DATOVÝ TOK

### 3.1 Import z Heliosu do aplikace

```
Helios Views (hvw_vok_Oresi_CP*)
         ↓
   Aplikace čte
         ↓
PostgreSQL tabulky:
  - travel.employee_profile
  - travel.vehicle
  - travel.rate
```

**Kdy se synchronizuje:**
- Při přihlášení uživatele
- Při načítání profilu zaměstnance
- Při načítání seznamu vozidel
- Při načítání kurzů a sazeb

### 3.2 Export z aplikace do Heliosu

```
PostgreSQL (travel.travel_order)
         ↓
   Aplikace exportuje
         ↓
MSSQL staging (dbo.vok_CPImportCestaky)
         ↓
    Helios čte
         ↓
View (dbo.vok_CPImportCestakyKImportu)
         ↓
Procedura (dbo.vok_CPImportCestak)
         ↓
Helios tabulky (TabICestak, TabIZakazky, TabIVozidla)
         ↓
  Callback do aplikace
         ↓
PostgreSQL - update statusu
```

**Kdy se exportuje:**
- Při schválení cestovního příkazu (status = 'approved')
- Spouští se automaticky synchronizační job
- Nebo ručně v Heliosu přes stored proceduru

---

## 4. ENVIRONMENT PROMĚNNÉ

### 4.1 Konfigurace ERP připojení

```bash
# MSSQL Server pro Helios
ERP_DB_SERVER=192.168.0.10
ERP_DB_NAME=HeliosDB
ERP_DB_USER=helios_user
ERP_DB_PASSWORD=secret123
ERP_DB_ENCRYPT=false

# Názvy views v Heliosu
ERP_USERS_VIEW=hvw_vok_Oresi_CPUzivatele
ERP_VEHICLES_VIEW=hvw_vok_Oresi_CPAuta
ERP_EXCHANGE_RATES_VIEW=hvw_vok_Oresi_CPKL
ERP_FOREIGN_COUNTRIES_VIEW=hvw_vok_Oresi_CPCestDZ
ERP_EXPENSE_CODES_VIEW=hvw_vok_Oresi_CPNaklKod

# API pro import callback
HELIOS_IMPORT_API_TOKEN=your-secret-token-here
HELIOS_IMPORT_LIST_URL=http://127.0.0.1:5055/api/helios/import-candidates?limit=500&shape=list
HELIOS_IMPORT_FULL_URL=http://127.0.0.1:5055/api/helios/import-candidates?limit=500
```

---

## 5. SOUBORY

### 5.1 Instalační skripty

| Soubor | Účel |
|--------|------|
| `docs/helios-mssql-staging-cestaky.sql` | Vytvoří staging tabulky a views |
| `docs/helios-create-procedure-import-cestak.sql` | Vytvoří stored proceduru pro import |
| `docs/helios-complete-setup-for-production.sql` | Kompletní setup pro produkci |

### 5.2 Synchronizační skripty

| Soubor | Účel |
|--------|------|
| `tools/sync_helios_import_queue.py` | Python skript pro synchronizaci staging tabulky |

---

## 6. API ENDPOINTY

### 6.1 Endpointy pro Helios

| Endpoint | Metoda | Účel |
|----------|--------|------|
| `/api/helios/import-candidates` | GET | Seznam cestovních příkazů k importu |
| `/api/helios/import-callback` | POST | Callback po dokončení importu v Heliosu |
| `/helios/preview` | GET | Náhled cestovního příkazu pro Helios |

### 6.2 Parametry `/api/helios/import-candidates`

**Query parametry:**
- `limit` - počet záznamů (default: 500)
- `shape` - formát výstupu: 'list' nebo 'full'

**Odpověď:**
```json
[
  {
    "importId": "7804C9B7-1FEC-4D6E-B6C5-47B6DB224B08",
    "orderNo": "CP-2026-0001",
    "approvedAt": "2026-05-19T14:30:00Z",
    "employeeNo": 12345,
    ...
  }
]
```

---

## 7. WORKFLOW

### 7.1 Standardní export workflow

1. **Uživatel vytvoří cestovní příkaz** v aplikaci
2. **Manažer schválí** → status = 'approved'
3. **Aplikace exportuje** do `vok_CPImportCestaky`
   - `ExportStatus` = 'queued'
   - `IsActive` = 1
   - Vyplní všechny sloupce
4. **Helios čte** z view `vok_CPImportCestakyKImportu`
5. **Helios spustí** proceduru `vok_CPImportCestak`
6. **Procedura importuje** do `TabICestak` a souvisejících tabulek
7. **Procedura zavolá callback** do aplikace s výsledkem
8. **Aplikace aktualizuje status**
   - `helios_exported_at` = aktuální čas
   - `helios_document_id` = číslo z Heliosu

### 7.2 Chybové stavy

**Když import selže:**
1. Procedura zapíše chybu do `ImportError`
2. Callback vrátí chybu do aplikace
3. Aplikace nastaví `helios_export_error`
4. Uživatel vidí chybu v UI
5. Admin může opravit data a spustit znovu

---

## 8. BEZPEČNOST

### 8.1 Autentizace

- **API Token:** Všechny požadavky z/do Heliosu používají token v hlavičce `X-Helios-Import-Token`
- **View oprávnění:** Helios uživatel musí mít SELECT práva na views
- **Procedura oprávnění:** Helios uživatel musí mít EXECUTE práva na proceduru

### 8.2 Validace

- **Osobní číslo:** Ověřuje se v ERP před exportem (`OsobniCisloOverenoVErp = 1`)
- **Středisko:** Kontroluje se existence v Heliosu
- **SPZ:** Validuje se formát před exportem

---

*Poslední aktualizace: 2026-05-19*
