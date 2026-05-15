-- Kontrola konfigurace pro callback v MSSQL
SELECT
    Klic AS 'Klic',
    Hodnota AS 'Hodnota',
    UpdatedAt AS 'Aktualizovano'
FROM dbo.vok_CPImportNastaveni
WHERE Klic IN (N'ImportResultsApiUrl', N'ImportApiToken')
ORDER BY Klic;
