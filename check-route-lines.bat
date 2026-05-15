@echo off
curl -H "X-Helios-Import-Token: QE78t52GjssT10cXSR2xrDvilmLzbmU5oiGpvcx5rPQ" "http://localhost:5055/api/helios/import-candidates?limit=1" > C:\CestovniPrikazy\payload-003.json
echo Payload ulozen do C:\CestovniPrikazy\payload-003.json
pause
