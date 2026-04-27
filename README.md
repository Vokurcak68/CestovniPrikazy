# Cestovní příkazy

Autonomní prototyp aplikace pro zadávání a schvalování tuzemských cestovních příkazů.

## Části projektu

- `travel-orders-app` - frontend aplikace v HTML/CSS/JavaScript.
- `travel-orders-server` - lokální Flask API pro přihlášení, profily, schvalování, sazby a odeslání příkazu.
- `database` - PostgreSQL schéma, migrace a seed lokálního administrátora.

## Lokální spuštění

1. Vytvoř PostgreSQL databázi podle `database/README.md`.
2. Spusť migrace ze složky `database/migrations`.
3. Spusť backend:

```powershell
.\travel-orders-server\start-local.ps1
```

4. Otevři aplikaci:

```text
http://127.0.0.1:5055
```

Pro testování z telefonu spusť server na hostu `0.0.0.0` a otevři lokální IP adresu počítače v síti.

## Stav prototypu

Aplikace zatím běží autonomně bez přímého napojení na Helios Inuvio/MSSQL. Databázová struktura a uživatelské profily jsou připravené tak, aby šla později doplnit synchronizace uživatelů, číselníků a export cestovních příkazů.
