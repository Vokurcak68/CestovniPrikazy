/*
  Fix callback URL to use internal network address instead of public domain.

  The MSSQL server at 192.168.0.131 cannot reach the public domain cp.kuchyneoresi.eu,
  so we need to use the internal IP address of the web server.

  Run this in the Helios MSSQL database.
*/

-- First, check the current configuration
SELECT 'Before Update' AS Status, Klic, Hodnota, UpdatedAt
FROM dbo.vok_CPImportNastaveni
WHERE Klic = N'ImportResultsApiUrl';

-- Update to use internal IP (assuming the web server is on the same machine or accessible locally)
-- Option 1: If Flask backend is on the same server as MSSQL
UPDATE dbo.vok_CPImportNastaveni
SET Hodnota = N'http://127.0.0.1:5055/api/helios/import-results',
    UpdatedAt = sysdatetime()
WHERE Klic = N'ImportResultsApiUrl';

-- Check the result
SELECT 'After Update' AS Status, Klic, Hodnota, UpdatedAt
FROM dbo.vok_CPImportNastaveni
WHERE Klic = N'ImportResultsApiUrl';

/*
  If the Flask backend is on a different server, you may need to use:
  - The internal IP address of the web server, e.g., http://192.168.0.XXX:5055/api/helios/import-results
  - Or if accessing through IIS, http://localhost/api/helios/import-results (if MSSQL and IIS are on same machine)
*/
