/*
  Select pro napojeni v Heliosu.

  Zdrojova data jsou v MSSQL staging tabulce dbo.vok_CPImportCestaky.
  Tabulku plni aplikace/synchronizacni job z cestovnich prikazu.
*/

SELECT
  ImportId,
  NahledUrl,
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
FROM dbo.vok_CPImportCestakyKImportu
ORDER BY
  SchvalenoDne DESC,
  CisloCestovnihoPrikazu;
