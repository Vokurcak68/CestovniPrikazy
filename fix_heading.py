#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re

with open(r'C:\CestovniPrikazy\travel-orders-server\app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the heading using regex - match any characters between <h2> and </h2> on that line
content = re.sub(
    r'(<h2>)[^<]*(dky vy)[^<]*(</h2>)',
    r'\1Řádky vyúčtování\3',
    content
)

with open(r'C:\CestovniPrikazy\travel-orders-server\app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed heading")
