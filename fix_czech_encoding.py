#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix Czech encoding in helios preview HTML"""

import re

# Read the file
with open(r'C:\CestovniPrikazy\travel-orders-server\app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Define replacements for helios preview section only (lines ~2398-2646)
# Find the render_helios_preview_html function and fix only that part
replacements = {
    'Oresi Â· CestovnĂ­ pĹ™Ă­kazy': 'Oresi · Cestovní příkazy',
    'Bez ÄŤĂ­sla': 'Bez čísla',
    'Bez ĂşÄŤelu': 'Bez účelu',
    'Bez cĂ­le': 'Bez cíle',
    'ZamÄ›stnanec': 'Zaměstnanec',
    'JmĂ©no': 'Jméno',
    'OsobnĂ­ ÄŤĂ­slo': 'Osobní číslo',
    'OvÄ›Ĺ™eno v ERP': 'Ověřeno v ERP',
    'StĹ™edisko': 'Středisko',
    'Cesta a schvĂˇlenĂ­': 'Cesta a schválení',
    'NavĹˇtĂ­venĂ© firmy': 'Navštívené firmy',
    'SpolucestujĂ­cĂ­': 'Spolucestující',
    'SchvĂˇleno': 'Schváleno',
    'CestovnĂ©': 'Cestovné',
    'StravnĂ©': 'Stravné',
    'OstatnĂ­ + doklady': 'Ostatní + doklady',
    'K vĂ˝platÄ›': 'K výplatě',
    'SpotĹ™eba': 'Spotřeba',
    'ImportnĂ­ kontrola': 'Importní kontrola',
    'Helios cestĂˇk ID': 'Helios cesták ID',
    'NaimportovĂˇno': 'Naimportováno',
    'PoÄŤet pĹ™Ă­loh': 'Počet příloh',
    'ĹĂˇdky vyĂşÄŤtovĂˇnĂ­': 'Řádky vyúčtování',
    '<h2>ĹĂˇdky vyĂşÄŤtovĂˇnĂ­</h2>': '<h2>Řádky vyúčtování</h2>',
    'Ř¡dky vy¡Â¨tovÂ¡nÂ­': 'Řádky vyúčtování',
    'L¬ÂAÂ¨dky vyÂÂsÂÂTtovÂÂÂnÂÂ': 'Řádky vyúčtování',
    'PĹ™Ă­jezd': 'Příjezd',
    'Příjezd': 'Příjezd',
    'Nejsou zadanĂ© ĹľĂˇdnĂ© Ĺ™Ăˇdky': 'Nejsou zadané žádné řádky',
    'Doklady a pĹ™Ă­lohy': 'Doklady a přílohy',
    'TuzemskÃ½': 'Tuzemský',
    'TuzemskÃ*': 'Tuzemský',
    'SoukromÃ©': 'Soukromé',
    'SoukromÂ©': 'Soukromé',
    'SoukromĂ˝': 'Soukromý',
    'TuzemskĂ˝': 'Tuzemský',
    'ZahraniÄŤnĂ­': 'Zahraniční',
    'SoukromĂ© vozidlo': 'Soukromé vozidlo',
    'SluĹľebnĂ­ vozidlo': 'Služební vozidlo',
    'VeĹ™ejnĂˇ doprava': 'Veřejná doprava',
    'JinĂ©': 'Jiné',
    'JĂ­zdnĂ©': 'Jízdné',
    'UbytovĂˇnĂ­': 'Ubytování',
    'ParkovnĂ©': 'Parkovné',
    'StravovĂˇnĂ­': 'Stravování',
    'OstatnĂ­ vĂ˝daj': 'Ostatní výdaj',
    'ĂšÄŤtenka': 'Účtenka',
    'JĂ­zdenka': 'Jízdenka',
    'JinĂ˝ doklad': 'Jiný doklad',
    # status_label
    'RozpracovĂˇno': 'Rozpracováno',
    'Ke schvĂˇlenĂ­': 'Ke schválení',
    'VyĂşÄŤtovĂˇnĂ­': 'Vyúčtování',
    'UzavĹ™eno': 'Uzavřeno',
    'ZamĂ­tnuto': 'Zamítnuto',
    'ZruĹˇeno': 'Zrušeno',
    # export_status_label
    'NepĹ™ipraveno': 'Nepřipraveno',
    'PĹ™ipraveno': 'Připraveno',
    'PĹ™™ipraveno': 'Připraveno',
    'Ve frontÄ›': 'Ve frontě',
    # Fix the mangled heading
    'LĂ¬ÂAÂ¨dky vyĂsĂTtovĂnĂ': 'Řádky vyúčtování',
    'L�A�dky vy�s�TtovÂ�nÂ�': 'Řádky vyúčtování',
    'K cestovnímu příkazu nejsou přiložené doklady.': 'K cestovnímu příkazu nejsou přiložené doklady.',
}

# Apply replacements
for old, new in replacements.items():
    content = content.replace(old, new)

# Write back
with open(r'C:\CestovniPrikazy\travel-orders-server\app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed Czech encoding in helios preview HTML")
