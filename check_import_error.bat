@echo off
sqlcmd -S 192.168.0.54 -d Helios002 -E -Q "SELECT TOP 5 ImportId, CisloCestovnihoPrikazu, ExportStatus, HeliosCestakId, ImportFinishedAt, ImportError FROM dbo.vok_CPImportCestaky ORDER BY ImportFinishedAt DESC;" -W -w 2000 -s"|"
