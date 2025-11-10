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
import time
from dataclasses import dataclass, field
import unicodedata
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
import traceback

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


def _insecure_ssl() -> bool:
    # Permite contornar ambientes sem cadeia de certificados correta
    # Use apenas para testes locais. Habilite via CLI --insecure ou env SEMA_INSECURE_SSL=1
    env = os.getenv('SEMA_INSECURE_SSL', '').strip()
    return env in ('1', 'true', 'TRUE', 'yes', 'on')


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


def _parse_date_any(s: str) -> Optional[datetime]:
    """Extrai uma data (prioriza dd/mm/aaaa ou dd_mm_aaaa) de um texto/URL e retorna datetime.
    Retorna None se não encontrar.
    """
    if not s:
        return None
    # dd[_-./]mm[_-./]yyyy
    m = re.search(r'(\d{1,2})[_.\-/](\d{1,2})[_.\-/](\d{2,4})', s)
    if m:
        d, mth, y = m.groups()
        try:
            yy = int(y)
            if yy < 100:
                yy += 2000
            return datetime(year=yy, month=int(mth), day=int(d))
        except Exception:
            return None
    return None


def fetch_laudo_index(limit: int = 5, timeout: int = 30, insecure: bool = False, max_retries: int = 3) -> List[Dict[str, str]]:
    """Coleta os últimos itens de laudos do site e retorna [{title, url}]."""
    for attempt in range(max_retries):
        try:
            r = requests.get(LAUDOS_URL, timeout=timeout, verify=not insecure, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; BalneabilidadeBot/0.1; +https://github.com/)'
            })
            r.raise_for_status()
            soup = BeautifulSoup(r.text, 'html.parser')
            break
        except requests.exceptions.SSLError as e:
            if not insecure:
                print('WARN: SSL inválido no índice da SEMA; tentando novamente sem verificação (confie antes de usar).')
                return fetch_laudo_index(limit=limit, timeout=timeout, insecure=True, max_retries=max_retries)
            print(f'WARN: falha ao acessar índice de laudos em {LAUDOS_URL}: {e}')
            if attempt == max_retries - 1:
                return []
            time.sleep(2 ** attempt)  # Exponential backoff
        except requests.RequestException as e:
            print(f'WARN: falha ao acessar índice de laudos em {LAUDOS_URL} (tentativa {attempt + 1}/{max_retries}): {e}')
            if attempt == max_retries - 1:
                print(f'ERROR: Falha final após {max_retries} tentativas. Verifique conectividade com {LAUDOS_URL}')
                return []
            time.sleep(2 ** attempt)  # Exponential backoff
    else:
        return []

    items: List[Dict[str, str]] = []
    # Heurística: buscar links para PDF ou páginas cujo contexto cite Laudo/Balneabilidade
    for a in soup.find_all('a', href=True):
        href = a['href'] or ''
        if not href:
            continue
        text = a.get_text(" ", strip=True) or ''
        # Coleta um pouco de contexto (pai imediato e avô) para achar datas/palavras-chave
        ctx_parts: List[str] = [text]
        try:
            parent = a.parent
            if parent is not None:
                ctx_parts.append(parent.get_text(" ", strip=True) or '')
                gp = getattr(parent, 'parent', None)
                if gp is not None and hasattr(gp, 'get_text'):
                    ctx_parts.append(gp.get_text(" ", strip=True) or '')
        except Exception:
            pass
        context_text = ' '.join([p for p in ctx_parts if p])

        href_abs = href if href.startswith('http') else requests.compat.urljoin(LAUDOS_URL, href)
        h = href.lower()
        t = (text or '').lower()
        c = (context_text or '').lower()

        looks_pdf = h.endswith('.pdf')
        mentions_laudo = ('laudo' in t) or ('balneabilidade' in t) or ('laudo' in c) or ('balneabilidade' in c)

        if looks_pdf or mentions_laudo:
            # extrai data de href, texto ou contexto (ex.: "período de ... a 15/09/2025")
            dt = _parse_date_any(href) or _parse_date_any(text) or _parse_date_any(context_text)
            ts = int(dt.timestamp()) if dt else 0
            items.append({'title': text, 'url': href_abs, 'ts': ts})

    # Remover duplicados conservando ordem
    seen = set()
    unique = []
    for it in items:
        key = it['url']
        if key in seen:
            continue
        seen.add(key)
        unique.append(it)

    # Ordena: prioriza PDFs e com data mais recente (ts maior)
    def sort_key(x: Dict[str, str]):
        ts = int(x.get('ts') or 0)
        is_pdf = 0 if x['url'].lower().endswith('.pdf') else 1
        # também prioriza se contiver 'balneabilidade' no caminho
        name_bias = 0 if ('balneabilidade' in x['url'].lower()) else 1
        # Prioridade: data mais recente primeiro; depois PDF; depois nome
        return (-ts, is_pdf, name_bias, -len(x.get('title') or ''))

    unique.sort(key=sort_key)
    top = unique[:limit]
    # Log curto dos candidatos (para visibilidade no Actions)
    print('Indexados (top):')
    for i, it in enumerate(top, 1):
        print(f"  {i:02d}. ts={it.get('ts',0)} url={it['url']}")
    return top


def download_pdf(url: str, timeout: int = 120, force: bool = False, insecure: bool = False, max_retries: int = 3) -> str:
    """Baixa um PDF para data/raw e devolve o caminho local."""
    name = re.sub(r'[^A-Za-z0-9._-]+', '_', os.path.basename(url))
    if not name.lower().endswith('.pdf'):
        name += '.pdf'
    path = os.path.join(RAW_DIR, name)
    if not force and os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    
    for attempt in range(max_retries):
        try:
            with requests.get(url, timeout=timeout, stream=True, verify=not insecure, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; BalneabilidadeBot/0.1; +https://github.com/)'
            }) as r:
                r.raise_for_status()
                with open(path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            return path
        except requests.exceptions.SSLError as e:
            if not insecure:
                print(f'WARN: SSL inválido ao baixar {url}; nova tentativa sem verificação (confira a procedência).')
                return download_pdf(url, timeout=timeout, force=force, insecure=True, max_retries=max_retries)
            print(f'WARN: falha SSL ao baixar {url} (tentativa {attempt + 1}/{max_retries}): {e}')
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)  # Exponential backoff
        except requests.RequestException as e:
            print(f'WARN: falha ao baixar {url} (tentativa {attempt + 1}/{max_retries}): {e}')
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)  # Exponential backoff
    return path


def resolve_pdf_from_page(url: str, timeout: int = 30, insecure: bool = False) -> Optional[str]:
    """Dado um URL de página (não-PDF), tenta encontrar um link para PDF dentro dela.
    Retorna o URL absoluto do PDF encontrado, priorizando caminhos que contenham
    'balneabilidade'. Caso não encontre, devolve None.
    """
    try:
        r = requests.get(url, timeout=timeout, verify=not insecure, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; BalneabilidadeBot/0.1; +https://github.com/)'
        })
        r.raise_for_status()
    except requests.exceptions.SSLError as e:
        if not insecure:
            print(f'WARN: SSL inválido na página {url}; tentando novamente sem verificação (confie antes de prosseguir).')
            return resolve_pdf_from_page(url, timeout=timeout, insecure=True)
        print(f'WARN: falha ao abrir página de laudo {url}: {e}')
        return None
    except requests.RequestException as e:
        print(f'WARN: falha ao abrir página de laudo {url}: {e}')
        return None

    soup = BeautifulSoup(r.text, 'html.parser')
    cand: List[str] = []
    for a in soup.find_all('a', href=True):
        href = a['href'] or ''
        if not href:
            continue
        if href.lower().endswith('.pdf'):
            abs_url = href if href.startswith('http') else requests.compat.urljoin(url, href)
            cand.append(abs_url)

    if not cand:
        return None
    # Prioriza PDFs que tenham 'balneabilidade' no nome
    cand.sort(key=lambda u: (0 if 'balneabilidade' in u.lower() else 1, len(u)))
    return cand[0]


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


def run(limit: int = 3, timeout: int = 120, from_file: Optional[str] = None, web_source_url: Optional[str] = None, refresh_raw: bool = False, insecure: Optional[bool] = None):
    ensure_dirs()
    items: List[Dict[str, str]] = []
    if from_file:
        # Usa um PDF local em vez de baixar
        items = [{'title': os.path.basename(from_file), 'url': f'file://{from_file}'}]
    else:
        # Define inseguro via CLI ou variável de ambiente
        insecure_flag = _insecure_ssl() if insecure is None else insecure
        items = fetch_laudo_index(limit=limit, timeout=timeout, insecure=insecure_flag)
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
            # Alguns laudos são páginas; tenta localizar PDF dentro da página
            resolved = resolve_pdf_from_page(url, timeout=timeout, insecure=insecure_flag)
            if not resolved:
                # Sem PDF interno, pula
                print(f'INFO: sem PDF encontrado na página {url} — ignorando')
                continue
            url = resolved
        try:
            pdf_path = download_pdf(url, timeout=timeout, force=refresh_raw, insecure=insecure_flag)
            rows = parse_pdf_text(pdf_path)
        except requests.RequestException as e:
            print(f'WARN: falha ao baixar PDF {url}: {e}')
            continue
        except Exception as e:
            print(f'WARN: erro ao processar PDF {url}: {e}')
            traceback.print_exc()
            continue
        # Anexa origem a cada linha para rastreio
        for r in rows:
            r['source_url'] = url
        all_rows.extend(rows)

    if not all_rows:
        print('Aviso: nenhuma linha extraída dos PDFs. Verifique regex/layout.')
        print('Possíveis causas:')
        print('  - Problemas de conectividade com o servidor da SEMA')
        print('  - PDFs com formato diferente do esperado')
        print('  - Mudanças na estrutura do site da SEMA')
        print('  - Restrições de acesso ou firewall')

    # Consolida por ponto
    # Se veio de arquivo local, preferir a URL web informada
    if from_file and web_source_url:
        source_url = web_source_url
    else:
        source_url = items[0]['url'] if items else LAUDOS_URL
    print(f"Fonte consolidada: {source_url}")
    agg = consolidate(all_rows, source_url)

    # Anexa geocódigos
    geos = load_geocodes(GEOCODES_CSV)
    attach_geocodes(agg, geos)

    # Emite JSON
    def _max_date_from_points(path: str) -> Optional[str]:
        try:
            if not os.path.exists(path):
                return None
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            dates = []
            for p in data:
                d = (p.get('latest') or {}).get('date')
                if d:
                    dates.append(d)
            return max(dates) if dates else None
        except Exception:
            return None

    if agg:
        points = to_points_json(agg)
        # Mantém log informativo, mas sempre escreve para refletir mudanças de conteúdo
        new_latest = None
        try:
            new_dates = [ (p.get('latest') or {}).get('date') for p in points ]
            new_dates = [d for d in new_dates if d]
            new_latest = max(new_dates) if new_dates else None
        except Exception:
            pass

        cur_latest = _max_date_from_points(POINTS_JSON)
        print(f"Comparação de versões (informativo): atual={cur_latest} novo={new_latest}")

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
    parser.add_argument('--timeout', type=int, default=120, help='Timeout de rede em segundos')
    parser.add_argument('--from-file', type=str, default=None, help='Caminho para PDF local (pula download)')
    parser.add_argument('--web-source-url', type=str, default=None, help='URL pública do laudo (para Fonte: SEMA/MA)')
    parser.add_argument('--refresh-raw', action='store_true', help='Força re-download dos PDFs em data/raw/')
    parser.add_argument('--insecure', action='store_true', default=None, help='Ignora verificação SSL (apenas testes locais)')
    args = parser.parse_args()
    run(limit=args.limit, timeout=args.timeout, from_file=args.from_file, web_source_url=args.web_source_url, refresh_raw=args.refresh_raw, insecure=args.insecure)
