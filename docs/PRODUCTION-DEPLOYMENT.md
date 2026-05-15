# Nasazení cestovních příkazů do produkce

Tento dokument popisuje, jak nasadit integraci cestovních příkazů do ostré databáze Heliosu.

## Přehled

Integrace umožňuje:
- Automatickou synchronizaci schválených cestovních příkazů z aplikace do Heliosu
- Import cestovních příkazů do Helios tabulek (TabICestak, TabICestaUsek, TabICestaNakl, TabICestaOsoba)
- Automatické generování soukromých jízd mezi služebními jízdami
- Callback do aplikace po úspěšném importu

## Požadavky

1. **SQL Server s ostrou databází Heliosu**
   - Přístup jako databázový administrátor (sa nebo db_owner)
   - SQL Server 2016 nebo novější

2. **Povolit Ole Automation Procedures** (pro HTTP callback)
   ```sql
   EXEC sp_configure 'show advanced options', 1;
   RECONFIGURE;
   EXEC sp_configure 'Ole Automation Procedures', 1;
   RECONFIGURE;
   ```

3. **Síťová konektivita**
   - MSSQL server musí mít přístup na https://cp.kuchyneoresi.eu

## Instalace

### Krok 1: Příprava skriptu

1. Otevři soubor `helios-complete-setup-for-production.sql`
2. Na řádku 22 **ZMĚŇ název databáze** na ostrou databázi:
   ```sql
   USE [NazevOstreDatabazeHeliosu]; -- ZMĚŇ NA NÁZEV OSTRÉ DATABÁZE!
   ```

### Krok 2: Spuštění setup skriptu

1. Připoj se k SQL Serveru jako administrátor (sa nebo db_owner role)
2. Otevři `helios-complete-setup-for-production.sql` v SQL Server Management Studio
3. Spusť celý skript (F5)
4. Zkontroluj výstup - měly by se objevit zelené ✓ značky u všech sekcí

### Krok 3: Úprava views pro tvou strukturu Heliosu

Views `hvw_vok_Oresi_CPUzivatele` a `hvw_vok_Oresi_CPAuta` jsou vytvořeny s defaultními sloupci. Možná budeš muset upravit SELECT dotazy podle struktury tvé databáze Heliosu:

```sql
-- View pro uživatele - UPRAV PODLE POTŘEBY
CREATE OR ALTER VIEW dbo.hvw_vok_Oresi_CPUzivatele
AS
SELECT
    OsCislo AS PersonalNumber,
    Jmeno AS FirstName,
    Prijmeni AS LastName,
    Email,
    1 AS IsActive
FROM dbo.TabOsoba
WHERE Email IS NOT NULL AND Email <> N'';

-- View pro vozidla - UPRAV PODLE POTŘEBY
CREATE OR ALTER VIEW dbo.hvw_vok_Oresi_CPAuta
AS
SELECT
    ID AS VehicleId,
    EvCislo AS RegistrationNumber,
    1 AS IsActive
FROM dbo.TabIVozidlo
WHERE EvCislo IS NOT NULL AND EvCislo <> N'';
```

### Krok 4: Ověření setup

Spusť následující dotaz pro kontrolu:

```sql
-- Kontrola tabulek
SELECT 'Tabulky' AS Typ, name AS Nazev
FROM sys.tables
WHERE name LIKE 'vok_CP%'
ORDER BY name;

-- Kontrola views
SELECT 'Views' AS Typ, name AS Nazev
FROM sys.views
WHERE name LIKE '%vok_%' OR name LIKE 'hvw_%'
ORDER BY name;

-- Kontrola procedur
SELECT 'Procedury' AS Typ, name AS Nazev
FROM sys.procedures
WHERE name LIKE 'vok_CP%'
ORDER BY name;

-- Kontrola konfigurace
SELECT 'Konfigurace' AS Typ, Klic, Hodnota
FROM dbo.vok_CPImportNastaveni
ORDER BY Klic;

-- Kontrola oprávnění pro uživatele zynaptec
SELECT
    OBJECT_NAME(major_id) AS ObjektNazev,
    permission_name AS Opravneni,
    state_desc AS Stav
FROM sys.database_permissions
WHERE grantee_principal_id = USER_ID('zynaptec')
ORDER BY OBJECT_NAME(major_id);
```

## Testování

### Test 1: Ověření views

```sql
-- Test view uživatelů
SELECT TOP 5 * FROM dbo.hvw_vok_Oresi_CPUzivatele;

-- Test view vozidel
SELECT TOP 5 * FROM dbo.hvw_vok_Oresi_CPAuta;
```

### Test 2: Schválení a synchronizace cestovního příkazu

1. V aplikaci vytvoř testovací cestovní příkaz
2. Odešli ho ke schválení
3. Schval ho
4. Počkej cca 1 minutu na automatickou synchronizaci
5. Zkontroluj, že se objevil v staging tabulce:

```sql
SELECT * FROM dbo.vok_CPImportCestakyPrehled
WHERE ExportStatus = 'ready'
ORDER BY CreatedAt DESC;
```

### Test 3: Dry run import

```sql
-- Najdi ImportId z předchozího dotazu
DECLARE @ImportId uniqueidentifier = '<ZKOPÍRUJ ImportId>';

-- Zkus dry run (test bez commitu)
EXEC dbo.vok_CPImportCestak
    @ImportId = @ImportId,
    @DryRun = 1;
```

Zkontroluj výsledek:
- `StavImportu` by měl být: "DRY RUN - rollback proveden"
- Neměly by se objevit žádné chyby

### Test 4: Ostrý import

```sql
DECLARE @ImportId uniqueidentifier = '<ZKOPÍRUJ ImportId>';

-- Ostrý import
EXEC dbo.vok_CPImportCestak
    @ImportId = @ImportId,
    @DryRun = 0;
```

Zkontroluj výsledek:
- `StavImportu` by měl být: "Import dokoncen, aplikace oznacena jako naimportovana"
- `TabICestakId` by měl obsahovat ID nově vytvořeného cestáku
- `CallbackHttpStatus` by měl být 200

### Test 5: Ověření v aplikaci

1. Otevři aplikaci
2. Najdi cestovní příkaz, který jsi importoval
3. Zkontroluj, že má stav "Exportováno" a je označen jako "Naimportováno do Heliosu"

### Test 6: Ověření v Helios tabulkách

```sql
-- Zkontroluj hlavní záznam cestáku
SELECT TOP 5 * FROM dbo.TabICestak
ORDER BY ID DESC;

-- Zkontroluj úseky (měly by tam být i soukromé jízdy 'S')
SELECT TOP 10 * FROM dbo.TabICestaUsek
ORDER BY idCestak DESC, Por;

-- Zkontroluj náklady (pokud byly nějaké)
SELECT TOP 5 * FROM dbo.TabICestaNakl
ORDER BY idCestak DESC;

-- Zkontroluj spolucestující (pokud byli)
SELECT TOP 5 * FROM dbo.TabICestaOsoba
ORDER BY idCestak DESC;
```

## Řešení problémů

### Problem: Callback selhal

**Příznaky:**
- `CallbackHttpStatus` je NULL
- `StavImportu` = "Import dokoncen, ale callback do aplikace selhal"

**Řešení:**
1. Zkontroluj síťovou konektivitu z MSSQL serveru:
   ```sql
   DECLARE @http int, @status int, @response varchar(8000);
   EXEC sp_OACreate 'MSXML2.ServerXMLHTTP.6.0', @http OUT;
   EXEC sp_OAMethod @http, 'open', NULL, 'GET', 'https://cp.kuchyneoresi.eu', false;
   EXEC sp_OAMethod @http, 'send', NULL, '';
   EXEC sp_OAGetProperty @http, 'status', @status OUT;
   SELECT @status AS HttpStatus;
   EXEC sp_OADestroy @http;
   ```
   Mělo by vrátit status 200.

2. Zkontroluj konfiguraci URL (NESMÍ obsahovat port :5055):
   ```sql
   SELECT * FROM dbo.vok_CPImportNastaveni
   WHERE Klic = 'ImportResultsApiUrl';
   ```
   Správná hodnota: `https://cp.kuchyneoresi.eu/api/helios/import-results`

3. Zkontroluj Ole Automation Procedures:
   ```sql
   EXEC sp_configure 'Ole Automation Procedures';
   ```
   Hodnota `run_value` by měla být 1.

### Problem: Import selhal s chybou

**Příznaky:**
- V `ImportError` sloupci je chybová zpráva
- Transakce byla rollbackována

**Řešení:**
1. Přečti si chybovou zprávu:
   ```sql
   SELECT ImportError FROM dbo.vok_CPImportCestaky
   WHERE ImportId = '<ImportId>';
   ```

2. Časté problémy:
   - **Nenalezen zaměstnanec**: View `hvw_vok_Oresi_CPUzivatele` nevrací správná data
   - **NULL hodnoty**: Nějaký povinný sloupec v Helios tabulkách nemá hodnotu
   - **Cizí klíče**: Neexistuje zákazka nebo vozidlo

### Problem: Cestovní příkaz se nesynchronizuje do MSSQL

**Řešení:**
1. Zkontroluj, že backend synchronizační skript běží
2. Zkontroluj logy backend serveru
3. Zkontroluj nastavení připojení v `.env`:
   ```
   ERP_DB_SERVER=192.168.0.131\sqlexpress
   ERP_DB_NAME=NazevOstreDatabazeHeliosu
   ERP_DB_USER=zynaptec
   ERP_DB_PASSWORD=15Z206n
   ```

## Údržba

### Vyčištění starých záznamů

Staging tabulka `vok_CPImportCestaky` může časem narůstat. Doporučujeme pravidelně mazat staré záznamy:

```sql
-- Smaž záznamy starší než 90 dní, které už jsou importované
DELETE FROM dbo.vok_CPImportCestaky
WHERE ExportStatus = 'exported'
  AND ImportFinishedAt < DATEADD(day, -90, GETDATE());
```

### Monitoring

Pravidelně kontroluj čekající importy:

```sql
-- Cestovní příkazy čekající na import
SELECT * FROM dbo.vok_CPImportCestakyPrehled
WHERE ExportStatus = 'ready'
ORDER BY CreatedAt DESC;

-- Cestovní příkazy s chybou
SELECT * FROM dbo.vok_CPImportCestakyPrehled
WHERE ImportError IS NOT NULL
ORDER BY CreatedAt DESC;
```

## Struktura objektů

### Tabulky
- `vok_CPImportCestaky` - Staging tabulka pro cestovní příkazy čekající na import
- `vok_CPImportNastaveni` - Konfigurace (URL, token)

### Views
- `vok_CPImportCestakyPrehled` - Přehled cestovních příkazů s rozparsovaným JSON payloadem
- `hvw_vok_Oresi_CPUzivatele` - View pro synchronizaci uživatelů z Heliosu
- `hvw_vok_Oresi_CPAuta` - View pro synchronizaci vozidel z Heliosu

### Stored Procedures
- `vok_CPImportCestak` - Hlavní procedura pro import cestovního příkazu do Heliosu

## Kontakt

V případě problémů kontaktuj vývojáře aplikace.
