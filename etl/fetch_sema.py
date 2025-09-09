"""
ETL: Laudos de Balneabilidade – SEMA/MA (esqueleto)

Fluxo:
1) Indexa a página de laudos para obter os links dos PDFs mais recentes;
2) Baixa PDFs para data/raw/;
3) Extrai pontos (código, praia, referência) e status por data (histórico);
4) Consolida lat/lng via data/stations_geocoded.csv;
5) Emite data/points.json para o mapa (web/app.js).

Observações:
- O layout real do PDF pode mudar; ajuste as regex/heurísticas em parse_pdf_text().
- Para uso em produção, trate duplicidades, normalização de datas e erros.
"""

import argparse
import json
import os
import re
from dataclasses import dataclass, field
import unicodedata
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

try:
    import pdfplumber  # type: ignore
except Exception:  # pragma: no cover - opcional
    pdfplumber = None

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA_DIR = os.path.join(ROOT, 'data')
RAW_DIR = os.path.join(DATA_DIR, 'raw')
GEOCODES_CSV = os.path.join(DATA_DIR, 'stations_geocoded.csv')
POINTS_JSON = os.path.join(DATA_DIR, 'points.json')

LAUDOS_URL = 'https://www.sema.ma.gov.br/laudos-de-balneabilidade'


@dataclass
class Sample:
    date: str
    status: str


@dataclass
class Station:
    code: str
    beach: Optional[str] = None
    reference: Optional[str] = None
    city: Optional[str] = None
    history: List[Sample] = field(default_factory=list)
    source_laudo: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(RAW_DIR, exist_ok=True)


def fetch_laudo_index(limit: int = 5, timeout: int = 30) -> List[Dict[str, str]]:
    """Coleta os últimos itens de laudos do site e retorna [{title, url}]."""
    r = requests.get(LAUDOS_URL, timeout=timeout, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; BalneabilidadeBot/0.1; +https://github.com/)'
    })
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')

    items: List[Dict[str, str]] = []
    # Heurística: buscar links que contenham 'Laudo' e/ou que apontem para PDFs
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.get_text(strip=True)
        if not href:
            continue
        if 'pdf' in href.lower() or 'Laudo' in text or 'laudo' in text:
            url = href if href.startswith('http') else requests.compat.urljoin(LAUDOS_URL, href)
            items.append({'title': text, 'url': url})

    # Remover duplicados conservando ordem
    seen = set()
    unique = []
    for it in items:
        key = it['url']
        if key in seen:
            continue
        seen.add(key)
        unique.append(it)

    # Heurística simples: priorizar PDFs
    unique.sort(key=lambda x: (0 if x['url'].lower().endswith('.pdf') else 1, -len(x['title'])))
    return unique[:limit]


def download_pdf(url: str, timeout: int = 60) -> str:
    """Baixa um PDF para data/raw e devolve o caminho local."""
    name = re.sub(r'[^A-Za-z0-9._-]+', '_', os.path.basename(url))
    if not name.lower().endswith('.pdf'):
        name += '.pdf'
    path = os.path.join(RAW_DIR, name)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    with requests.get(url, timeout=timeout, stream=True, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; BalneabilidadeBot/0.1; +https://github.com/)'
    }) as r:
        r.raise_for_status()
        with open(path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    return path


def parse_pdf_text(pdf_path: str) -> List[Dict[str, str]]:
    """
    Extrai linhas relevantes do PDF. Ajuste conforme o layout real.

    Retorna uma lista de dicts brutos por ponto, por exemplo:
      {
        'code': 'P19', 'beach': 'Olho de Porco', 'reference': '...',
        'status': 'PRÓPRIO', 'date': '2025-09-01'
      }
    Poderá retornar múltiplas entradas por ponto (histórico) dependendo do PDF.
    """
    if pdfplumber is None:
        # Sem pdfplumber, devolve vazio; usar stub ou instalar dependência
        return []

    results: List[Dict[str, str]] = []
    with pdfplumber.open(pdf_path) as pdf:
        text_pages: List[str] = []
        for page in pdf.pages:
            # Tenta primeiro com boa tolerância horizontal/vertical
            page_text = page.extract_text(x_tolerance=1.5, y_tolerance=3) or ''
            text_pages.append(page_text)
        text = '\n'.join(text_pages)

    # Normalizações simples
    norm = re.sub(r'\s+', ' ', text)
    # Também manter uma versão com quebras de linha para parsing por blocos
    text_nl = text

    # Tentar capturar período do laudo (data mais recente)
    # Ex.: "período de 21/07/2025 a 21/08/2025"
    m = re.search(r'período de (\d{2}/\d{2}/\d{4}) a (\d{2}/\d{2}/\d{4})', norm, re.IGNORECASE)
    laudo_to = None
    if m:
        laudo_to = m.group(2)

    def strip_accents(txt: str) -> str:
        return ''.join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

    def normalize_status_text(s: Optional[str]) -> str:
        raw = (s or '').upper().replace('"', '').replace("'", '').replace('`', '')
        ascii_ = strip_accents(raw)
        if 'IMPROPRIO' in ascii_:
            return 'IMPRÓPRIO'
        if 'PROPRIO' in ascii_:
            return 'PRÓPRIO'
        return raw or 'DESCONHECIDO'

    # Heurística 1 (por blocos): separar por códigos Pxx e buscar campos por linha
    split_codes = re.split(r'(P\d{1,3})', text_nl)
    if len(split_codes) > 1:
        it = iter(split_codes)
        preamble = next(it, '')  # texto antes do primeiro código (ignorado)
        for code in it:
            chunk = next(it, '')
            code_up = code.strip().upper()
            # Delimitar o bloco até o próximo código (já segmentado pelo split)
            block = chunk.strip()
            if not block:
                continue
            # Capturar campos principais em modo linha
            def find_line(pats: List[str]) -> Optional[str]:
                for pat in pats:
                    m = re.search(pat, block, re.IGNORECASE)
                    if m:
                        return m.group(1).strip(' :-')
                return None

            beach = find_line([
                r'^\s*Praia\s*:?\s*(.+)$',
                r'\bPraia\s*:?\s*(.+)$',
            ])

            reference = find_line([
                r'Ponto\s+de\s+refer(?:ê|e)ncia\s*:?\s*(.+)$',
                r'Refer[eê]ncia\s*:?\s*(.+)$',
                r'Ref\.?\s*:?\s*(.+)$',
            ])

            date = find_line([r'Data\s+da\s+coleta\s*:?\s*(\d{2}/\d{2}/\d{4})']) or laudo_to or ''

            status_m = re.search(r'\b(IMPR[ÓO]PRIO|PR[ÓO]PRIO|IMPROPRIO|PROPRIO|IMPRPRIO)\b', block, re.IGNORECASE)
            status = normalize_status_text(status_m.group(1) if status_m else None)

            if status:
                results.append({
                    'code': code_up,
                    'beach': beach or '',
                    'reference': reference or '',
                    'status': status,
                    'date': date or ''
                })

    # Heurística 2: blocos no texto linear "Praia: X Ponto de referência: Y Data: Z Status: W"
    block_pat = re.compile(
        r'(P\d{1,3})[^P]*?Praia:\s*(.*?)\s*(?:Ponto\s+de\s+refer(?:ê|e)ncia|Ponto\s+de\s+referencia|Refer[eê]ncia|Ref\.):\s*(.*?)\s*(?:Data\s+da\s+coleta:)?\s*(\d{2}/\d{2}/\d{4})?[^S]*?Status:\s*([A-ZÇÃÓÍÉÊÀÂÕÚ]+)',
        re.IGNORECASE
    )

    for match in block_pat.finditer(norm):
        code = match.group(1).upper()
        beach = (match.group(2) or '').strip(' :-')
        reference = (match.group(3) or '').strip(' :-')
        date = match.group(4) or laudo_to or ''
        status = normalize_status_text(match.group(5))
        if code and status:
            results.append({
                'code': code,
                'beach': beach,
                'reference': reference,
                'status': status,
                'date': date
            })

    # Heurística 2 (fallback): tentar tabelas no texto contendo "Pxx" e status
    if not results:
        # Fallback genérico: linhas compactas com código, praia, referência e status
        row_pat = re.compile(r'(P\d{1,3}).{0,80}?([A-Za-zÀ-ÿ\'\- ]+).{0,200}?\b(?:Ponto\s+de\s+refer(?:ê|e)ncia|Refer[eê]ncia|Ref\.)\s*:?\s*([^\n\r]+?)\s+(?:Data\s+da\s+coleta\s*:?\s*(\d{2}/\d{2}/\d{4}))?.{0,80}?\b(PR[ÓO]PRIO|IMPR[ÓO]PRIO)\b', re.IGNORECASE)
        for m2 in row_pat.finditer(norm):
            code = m2.group(1).upper()
            beach = (m2.group(2) or '').strip()
            reference = (m2.group(3) or '').strip()
            date = (m2.group(4) or '') or laudo_to or ''
            status = normalize_status_text(m2.group(5))
            results.append({
                'code': code,
                'beach': beach,
                'reference': reference,
                'status': status,
                'date': date
            })

    # Heurística 3: tentar capturar "Série histórica" próxima do bloco
    # Busca até 300 caracteres após cada match por pares data-status
    hist_pair = re.compile(r'(\d{2}/\d{2}/\d{4})\s*[-–—]\s*(PR[ÓO]PRIO|IMPR[ÓO]PRIO)', re.IGNORECASE)
    if results:
        # Revarre o texto original por janelas com base no código do ponto
        for i, item in enumerate(results):
            code = item['code']
            mcode = re.search(re.escape(code), norm)
            if not mcode:
                continue
            start = mcode.end()
            window = norm[start:start+300]
            for h in hist_pair.finditer(window):
                d = parse_date_br(h.group(1))
                s = normalize_status_text(h.group(2))
                # Insere como linhas extras; a consolidação agrupa por ponto
                results.append({
                    'code': code,
                    'beach': item.get('beach') or '',
                    'reference': item.get('reference') or '',
                    'status': s,
                    'date': d
                })

    return results


def parse_date_br(s: str) -> str:
    try:
        return datetime.strptime(s, '%d/%m/%Y').strftime('%Y-%m-%d')
    except Exception:
        return s


def load_geocodes(path: str) -> Dict[str, Dict[str, str]]:
    geos: Dict[str, Dict[str, str]] = {}
    if not os.path.exists(path):
        return geos
    with open(path, 'r', encoding='utf-8') as f:
        header = f.readline()
        for line in f:
            if not line.strip():
                continue
            # Divide em 6 colunas no máximo, preservando vírgulas dentro de aspas
            parts = re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', line.strip())
            parts = [p.strip().strip('"') for p in parts]
            code, beach, reference, city, lat, lng = (parts + ['',''])[:6]
            geos[code.strip().upper()] = {
                'beach': beach,
                'reference': reference,
                'city': city,
                'lat': lat,
                'lng': lng,
            }
    return geos


def consolidate(stations_raw: List[Dict[str, str]], source_url: str) -> Dict[str, Station]:
    agg: Dict[str, Station] = {}
    for row in stations_raw:
        code = row.get('code', '').upper()
        if not code:
            continue
        s = agg.get(code) or Station(code=code)
        s.beach = s.beach or row.get('beach')
        s.reference = s.reference or row.get('reference')
        date_iso = parse_date_br(row.get('date', ''))
        # Normaliza status ainda na consolidação para garantir canônico
        status = (row.get('status') or '')
        # Reusa mesma lógica de normalização do parser
        try:
            import unicodedata as _u
            def _strip(t):
                return ''.join(c for c in _u.normalize('NFD', t) if _u.category(c) != 'Mn')
            raw = status.upper().replace('"','').replace("'",'').replace('`','')
            ascii_ = _strip(raw)
            if 'IMPROPRIO' in ascii_:
                status = 'IMPRÓPRIO'
            elif 'PROPRIO' in ascii_:
                status = 'PRÓPRIO'
        except Exception:
            status = status.upper()
        if date_iso and status:
            s.history.append(Sample(date=date_iso, status=status))
        s.source_laudo = s.source_laudo or source_url
        agg[code] = s
    return agg


def attach_geocodes(agg: Dict[str, Station], geos: Dict[str, Dict[str, str]]):
    for code, s in agg.items():
        g = geos.get(code)
        if not g:
            continue
        # Assume stations_geocoded.csv como fonte da verdade textual
        if g.get('city'):
            s.city = g['city']
        if g.get('beach'):
            s.beach = g['beach']
        if g.get('reference'):
            s.reference = g['reference']
        try:
            s.lat = float(g.get('lat') or '')
            s.lng = float(g.get('lng') or '')
        except Exception:
            pass


def to_points_json(agg: Dict[str, Station]) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    for s in agg.values():
        hist_sorted = sorted({(h.date, h.status) for h in s.history}, key=lambda x: x[0])
        latest = hist_sorted[-1] if hist_sorted else None
        out.append({
            'code': s.code,
            'beach': s.beach,
            'reference': s.reference,
            'city': s.city,
            'lat': s.lat,
            'lng': s.lng,
            'latest': {'date': latest[0], 'status': latest[1]} if latest else None,
            'history': [{'date': d, 'status': st} for (d, st) in hist_sorted],
            'source_laudo': s.source_laudo,
        })
    # Ordena para estabilidade
    out.sort(key=lambda x: x['code'])
    return out


def write_stations_index_csv(agg: Dict[str, Station], path: str):
    # Gera um índice para facilitar preenchimento de coordenadas oficiais
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write('code,beach,reference,city,lat,lng\n')
        for s in sorted(agg.values(), key=lambda x: x.code):
            lat = '' if s.lat is None else str(s.lat)
            lng = '' if s.lng is None else str(s.lng)
            b = (s.beach or '').replace('"', "'")
            r = (s.reference or '').replace('"', "'")
            c = (s.city or '').replace('"', "'")
            f.write(f'{s.code},"{b}","{r}","{c}",{lat},{lng}\n')


def run(limit: int = 3, timeout: int = 60, from_file: Optional[str] = None, web_source_url: Optional[str] = None):
    ensure_dirs()
    items: List[Dict[str, str]] = []
    if from_file:
        # Usa um PDF local em vez de baixar
        items = [{'title': os.path.basename(from_file), 'url': f'file://{from_file}'}]
    else:
        items = fetch_laudo_index(limit=limit, timeout=timeout)
    all_rows: List[Dict[str, str]] = []
    for it in items:
        url = it['url']
        if url.startswith('file://'):
            pdf_path = url.replace('file://', '')
            rows = parse_pdf_text(pdf_path)
            for r in rows:
                r['source_url'] = web_source_url or url
            all_rows.extend(rows)
            continue
        if not url.lower().endswith('.pdf'):
            # Pular itens não-PDF; em alguns casos a página do laudo tem link para PDF interno
            continue
        pdf_path = download_pdf(url, timeout=timeout)
        rows = parse_pdf_text(pdf_path)
        # Anexa origem a cada linha para rastreio
        for r in rows:
            r['source_url'] = url
        all_rows.extend(rows)

    if not all_rows:
        print('Aviso: nenhuma linha extraída dos PDFs. Verifique regex/layout.')

    # Consolida por ponto
    # Se veio de arquivo local, preferir a URL web informada
    if from_file and web_source_url:
        source_url = web_source_url
    else:
        source_url = items[0]['url'] if items else LAUDOS_URL
    agg = consolidate(all_rows, source_url)

    # Anexa geocódigos
    geos = load_geocodes(GEOCODES_CSV)
    attach_geocodes(agg, geos)

    # Emite JSON
    if agg:
        points = to_points_json(agg)
        with open(POINTS_JSON, 'w', encoding='utf-8') as f:
            json.dump(points, f, ensure_ascii=False, indent=2)
        print(f'Gerado: {POINTS_JSON} (itens={len(points)})')
    else:
        print('Sem pontos consolidados – mantendo points.json atual (se existir).')

    # Escreve também um índice para facilitar preenchimento de coordenadas
    stations_index_csv = os.path.join(DATA_DIR, 'stations_index.csv')
    write_stations_index_csv(agg, stations_index_csv)
    print(f'Gerado: {stations_index_csv}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='ETL de laudos de balneabilidade – SEMA/MA')
    parser.add_argument('--limit', type=int, default=5, help='Número máximo de laudos para indexar/baixar')
    parser.add_argument('--timeout', type=int, default=60, help='Timeout de rede em segundos')
    parser.add_argument('--from-file', type=str, default=None, help='Caminho para PDF local (pula download)')
    parser.add_argument('--web-source-url', type=str, default=None, help='URL pública do laudo (para Fonte: SEMA/MA)')
    args = parser.parse_args()
    run(limit=args.limit, timeout=args.timeout, from_file=args.from_file, web_source_url=args.web_source_url)
