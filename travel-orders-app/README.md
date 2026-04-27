# Cestovní příkazy

První autonomní prototyp aplikace pro tuzemské cestovní příkazy. Aplikace je zatím čistě statická a neobsahuje napojení na Helios, MSSQL ani jinou databázi.

## Spuštění bez backendu

Otevřete `index.html` v prohlížeči.

Data se ukládají lokálně do `localStorage` daného prohlížeče. Tlačítko `Export` stáhne zálohu ve formátu JSON.

## Spuštění s lokálním přihlášením

Spusťte backend:

```powershell
.\travel-orders-server\start-local.ps1
```

Potom otevřete:

```text
http://127.0.0.1:5055
```

Přihlášení se ověřuje proti lokální PostgreSQL databázi.

## Obsah prototypu

- evidence cestovních příkazů,
- základní údaje zaměstnance a organizace,
- údaje o cestě,
- vozidlo, PHM a základní náhrada za km,
- neomezený počet řádků vyúčtování,
- výpočet cestovného, stravného, nocležného, vedlejších výdajů a doplatku/přeplatku,
- stavový tok: rozpracováno, ke schválení, schváleno, vyúčtování, uzavřeno, zamítnuto,
- tiskový/PDF výstup přes tisk prohlížeče,
- editovatelné sazby pro rok 2026.

## Další krok

Po odsouhlasení obrazovek a výpočtů dává smysl rozdělit prototyp na:

- frontend,
- backend API,
- PostgreSQL databázi,
- autentizaci,
- integrační vrstvu pro Helios.
