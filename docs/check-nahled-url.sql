-- Check current configuration
SELECT 'Configuration' AS Section, Klic, Hodnota, UpdatedAt
FROM dbo.vok_CPImportNastaveni
WHERE Klic IN (N'TravelOrderPreviewUrl', N'ImportApiToken')

UNION ALL

-- Check NahledUrl for recent orders
SELECT 'Sample URLs' AS Section,
  CisloCestovnihoPrikazu AS Klic,
  NahledUrl AS Hodnota,
  SchvalenoDne AS UpdatedAt
FROM dbo.vok_CPImportCestakyKImportu
WHERE CisloCestovnihoPrikazu IN (N'CP-2026-0003', N'CP-2026-0004')
ORDER BY Section DESC, Klic;
