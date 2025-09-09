"""
Valida cobertura de coordenadas vs. pontos detectados.

Uso (após gerar stations_index.csv):
  python etl/validate_geocodes.py
"""

import csv
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA_DIR = os.path.join(ROOT, 'data')
INDEX_CSV = os.path.join(DATA_DIR, 'stations_index.csv')
GEOCODES_CSV = os.path.join(DATA_DIR, 'stations_geocoded.csv')


def read_csv_codes(path):
    if not os.path.exists(path):
        return {}
    out = {}
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = (row.get('code') or '').strip().upper()
            if not code:
                continue
            out[code] = row
    return out


def main():
    idx = read_csv_codes(INDEX_CSV)
    geo = read_csv_codes(GEOCODES_CSV)
    if not idx:
        print('Gere primeiro data/stations_index.csv via etl/fetch_sema.py')
        return
    missing = []
    for code, row in idx.items():
        g = geo.get(code)
        if not g or not (g.get('lat') and g.get('lng')):
            missing.append((code, row.get('beach') or '', row.get('reference') or ''))
    print(f'Total pontos detectados: {len(idx)}')
    print(f'Faltam coordenadas: {len(missing)}')
    if missing:
        print('Exemplos ausentes:')
        for code, beach, ref in missing[:10]:
            print(f' - {code} | {beach} | {ref}')


if __name__ == '__main__':
    main()

