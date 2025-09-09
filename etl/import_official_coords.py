"""
Importa coordenadas oficiais para stations_geocoded.csv

Uso:
  python etl/import_official_coords.py --src caminho/do/arquivo.csv

Formato aceito (header flexível):
  - code,lat,lng
  - code,beach,reference,city,lat,lng

O script faz merge por "code" e preserva beach/reference/city existentes
no stations_geocoded.csv quando o CSV de origem não fornecer.
"""

import argparse
import csv
import os
from typing import Dict, Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA_DIR = os.path.join(ROOT, 'data')
GEOCODES_CSV = os.path.join(DATA_DIR, 'stations_geocoded.csv')


def read_csv_map(path: str) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if not os.path.exists(path):
        return out
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = (row.get('code') or '').strip().upper()
            if not code:
                continue
            out[code] = {
                'code': code,
                'beach': row.get('beach') or '',
                'reference': row.get('reference') or '',
                'city': row.get('city') or '',
                'lat': row.get('lat') or '',
                'lng': row.get('lng') or '',
            }
    return out


def write_csv_map(path: str, data: Dict[str, Dict[str, Any]]):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['code', 'beach', 'reference', 'city', 'lat', 'lng'])
        writer.writeheader()
        for code in sorted(data.keys()):
            writer.writerow(data[code])


def main(src: str):
    current = read_csv_map(GEOCODES_CSV)
    incoming = read_csv_map(src)
    if not incoming:
        print('Nada para importar: arquivo vazio ou inválido.')
        return

    for code, row in incoming.items():
        existing = current.get(code, {'code': code, 'beach': '', 'reference': '', 'city': '', 'lat': '', 'lng': ''})
        # Merge: dados oficiais prevalecem quando presentes
        merged = {
            'code': code,
            'beach': row.get('beach') or existing.get('beach') or '',
            'reference': row.get('reference') or existing.get('reference') or '',
            'city': row.get('city') or existing.get('city') or '',
            'lat': row.get('lat') or existing.get('lat') or '',
            'lng': row.get('lng') or existing.get('lng') or '',
        }
        current[code] = merged

    write_csv_map(GEOCODES_CSV, current)
    print(f'Merge concluído em: {GEOCODES_CSV} (registros: {len(current)})')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Importar coordenadas oficiais para stations_geocoded.csv')
    parser.add_argument('--src', required=True, help='Caminho para CSV oficial (code,lat,lng ou code,beach,reference,city,lat,lng)')
    args = parser.parse_args()
    main(args.src)

