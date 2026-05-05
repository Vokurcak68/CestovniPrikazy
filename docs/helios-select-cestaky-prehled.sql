/*
  Prehled vsech cestovnich prikazu ve stagingu vcetne uz importovanych.
  Pouzij pro dohledani odkazu na read-only nahled i po importu do Heliosu.
*/

SELECT
  ImportId,
  NahledUrl,
  CisloCestovnihoPrikazu,
  Zamestnanec,
  CisloZamestnance,
  SchvalenoDne,
  ExportStatus,
  IsActive,
  HeliosCestakId,
  StavImportu,
  SyncedAt
FROM dbo.vok_CPImportCestakyPrehled
ORDER BY
  SyncedAt DESC,
  CisloCestovnihoPrikazu;
