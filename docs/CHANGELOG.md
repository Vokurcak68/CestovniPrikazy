# Changelog

## 2026-05-06
- Oprava login/registrace: login uz nepouziva `password_confirm`.
- Admin mazani uzivatelu:
  - doplnen backend endpoint pro smazani
  - pridana ochrana proti self-delete
  - blokace mazani ERP uzivatelu (`helios` / `mixed` / `helios_user_id`)
- Oprava submit workflow:
  - validace povinnych business poli pri submitu
  - frontend hlasky pro nove validacni chyby
- Oprava kolizi cisla cestaku:
  - backend zajisti unikatni `order_no`
  - frontend prevezme finalni cislo ze serveru po submitu
- Oprava nekonzistentnich dat mezi uzivateli/PC:
  - izolace lokalniho stavu podle uzivatele
  - hydration detailu ze server snapshotu
- Oprava cestiny v Upozornenich:
  - oprava novych textu na backendu
  - frontend fallback oprava historickych "mojibake" textu
- Provozni stabilizace:
  - pridany `STABILIZATION_CHECKLIST.md`
  - pridany `RUNBOOK.md`
  - pridany `KNOWN_RISKS.md`
  - pridany `tools/check_data_integrity.py`
