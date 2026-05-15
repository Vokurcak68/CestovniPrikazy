
PRINT '   ✓ Procedura dbo.vok_CPImportCestak vytvořena';

-- ============================================================================
-- 6. NASTAVENÍ OPRÁVNĚNÍ PRO UŽIVATELE ZYNAPTEC
-- ============================================================================
PRINT '';
PRINT '6. Nastavování oprávnění pro uživatele zynaptec...';

-- Tabulky - SELECT, INSERT, UPDATE
PRINT '   Udělování oprávnění na tabulky...';
GRANT SELECT, INSERT, UPDATE ON dbo.vok_CPImportCestaky TO [zynaptec];
GRANT SELECT, INSERT, UPDATE ON dbo.vok_CPImportNastaveni TO [zynaptec];

-- Helios tabulky - pouze SELECT na čtení
GRANT SELECT ON dbo.TabOsoba TO [zynaptec];
GRANT SELECT ON dbo.TabIVozidlo TO [zynaptec];
GRANT SELECT ON dbo.TabZakazka TO [zynaptec];

-- Helios tabulky - SELECT, INSERT pro zápis cestovních příkazů
GRANT SELECT, INSERT ON dbo.TabICestak TO [zynaptec];
GRANT SELECT, INSERT ON dbo.TabICestaUsek TO [zynaptec];
GRANT SELECT, INSERT ON dbo.TabICestaNakl TO [zynaptec];
GRANT SELECT, INSERT ON dbo.TabICestaOsoba TO [zynaptec];

-- Views
PRINT '   Udělování oprávnění na views...';
GRANT SELECT ON dbo.vok_CPImportCestakyPrehled TO [zynaptec];
GRANT SELECT ON dbo.hvw_vok_Oresi_CPUzivatele TO [zynaptec];
GRANT SELECT ON dbo.hvw_vok_Oresi_CPAuta TO [zynaptec];

-- Stored procedury
PRINT '   Udělování oprávnění na stored procedury...';
GRANT EXECUTE ON dbo.vok_CPImportCestak TO [zynaptec];

-- Oprávnění pro OLE Automation (pokud ještě nejsou nastavena)
PRINT '   Kontrola oprávnění pro OLE Automation...';
IF NOT EXISTS (
    SELECT 1
    FROM sys.server_role_members srm
    JOIN sys.server_principals sp ON srm.member_principal_id = sp.principal_id
    WHERE sp.name = N'zynaptec'
      AND srm.role_principal_id = (
          SELECT principal_id FROM sys.server_principals WHERE name = N'sysadmin'
      )
)
BEGIN
    -- Pokud uživatel není sysadmin, potřebuje specifická oprávnění pro sp_OA*
    PRINT '   VAROVÁNÍ: Uživatel zynaptec není sysadmin.';
    PRINT '   Pro callback funkce (sp_OACreate, sp_OAMethod, atd.) může být potřeba:';
    PRINT '   - Povolit Ole Automation Procedures na server úrovni';
    PRINT '   - Nebo přidat uživatele do role pro OLE Automation';
    PRINT '';
    PRINT '   Spusť jako sa:';
    PRINT '     EXEC sp_configure ''Ole Automation Procedures'', 1;';
    PRINT '     RECONFIGURE;';
END
ELSE
BEGIN
    PRINT '   ✓ Uživatel má dostatečná oprávnění (sysadmin)';
END

PRINT '   ✓ Oprávnění nastavena';

-- ============================================================================
-- 7. OVĚŘENÍ SETUP
-- ============================================================================
PRINT '';
PRINT '7. Ověření setup...';

-- Kontrola tabulek
DECLARE @TableCount int;
SELECT @TableCount = COUNT(*)
FROM sys.tables
WHERE name IN (N'vok_CPImportCestaky', N'vok_CPImportNastaveni');

IF @TableCount = 2
    PRINT '   ✓ Všechny tabulky vytvořeny';
ELSE
    PRINT '   ✗ Některé tabulky chybí!';

-- Kontrola views
DECLARE @ViewCount int;
SELECT @ViewCount = COUNT(*)
FROM sys.views
WHERE name IN (N'vok_CPImportCestakyPrehled', N'hvw_vok_Oresi_CPUzivatele', N'hvw_vok_Oresi_CPAuta');

IF @ViewCount = 3
    PRINT '   ✓ Všechny views vytvořeny';
ELSE
    PRINT '   ✗ Některé views chybí!';

-- Kontrola procedur
DECLARE @ProcCount int;
SELECT @ProcCount = COUNT(*)
FROM sys.procedures
WHERE name = N'vok_CPImportCestak';

IF @ProcCount = 1
    PRINT '   ✓ Stored procedura vytvořena';
ELSE
    PRINT '   ✗ Stored procedura chybí!';

-- Kontrola konfigurace
DECLARE @ConfigCount int;
SELECT @ConfigCount = COUNT(*)
FROM dbo.vok_CPImportNastaveni
WHERE Klic IN (N'ImportResultsApiUrl', N'TravelOrderPreviewUrl', N'ImportApiToken');

IF @ConfigCount = 3
    PRINT '   ✓ Konfigurace nastavena';
ELSE
    PRINT '   ✗ Konfigurace není kompletní!';

-- Kontrola uživatele
IF EXISTS (SELECT * FROM sys.database_principals WHERE name = N'zynaptec')
    PRINT '   ✓ Uživatel zynaptec existuje';
ELSE
    PRINT '   ✗ Uživatel zynaptec chybí!';

-- ============================================================================
-- HOTOVO
-- ============================================================================
PRINT '';
PRINT '========================================';
PRINT 'SETUP DOKONČEN!';
PRINT '========================================';
PRINT '';
PRINT 'Další kroky:';
PRINT '1. Zkontroluj views hvw_vok_Oresi_CPUzivatele a hvw_vok_Oresi_CPAuta';
PRINT '   - Přizpůsob SELECT dotazy podle struktury tvých Helios tabulek';
PRINT '';
PRINT '2. Otestuj import cestovního příkazu:';
PRINT '   - Schval cestovní příkaz v aplikaci';
PRINT '   - Počkej na automatickou synchronizaci do staging tabulky';
PRINT '   - Spusť import pomocí:';
PRINT '     SELECT * FROM dbo.vok_CPImportCestakyPrehled WHERE ExportStatus = ''ready'';';
PRINT '     EXEC dbo.vok_CPImportCestak @ImportId = ''<UUID>'', @DryRun = 1;';
PRINT '     -- Pokud test projde OK, spusť ostře:';
PRINT '     EXEC dbo.vok_CPImportCestak @ImportId = ''<UUID>'', @DryRun = 0;';
PRINT '';
PRINT '3. Zkontroluj callback:';
PRINT '   - Po úspěšném importu by se měl zavolat callback do aplikace';
PRINT '   - Ověř, že cestovní příkaz v aplikaci má stav "Exportováno"';
PRINT '';
GO
