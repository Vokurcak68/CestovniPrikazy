/*
  Spustit pod MSSQL uctem, ktery ma pravo spravovat schema dbo v databazi Helios002.

  Varianta A - doporucena:
  1. admin spusti docs/helios-mssql-staging-cestaky.sql
  2. admin spusti granty nize
  3. aplikacni sync se pousti s --skip-schema

  Tim ucet zynaptec nemusi mit CREATE TABLE / CREATE VIEW.
*/

GRANT SELECT, INSERT, UPDATE ON dbo.vok_CPImportCestaky TO zynaptec;
GRANT SELECT ON dbo.vok_CPImportNastaveni TO zynaptec;
GRANT SELECT ON dbo.vok_CPImportCestakyPrehled TO zynaptec;
GRANT SELECT ON dbo.vok_CPImportCestakyKImportu TO zynaptec;

/*
  Varianta B - pokud ma aplikace sama zakladat nebo aktualizovat staging objekty:
  Pozor, je sirsi. Pouzij jen pokud nechces DDL poustet pod adminem.

  GRANT CREATE TABLE TO zynaptec;
  GRANT CREATE VIEW TO zynaptec;
  GRANT ALTER ON SCHEMA::dbo TO zynaptec;
*/
