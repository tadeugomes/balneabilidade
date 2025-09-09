const MAP_CENTER = [-2.50, -44.27]; // São Luís (aprox.)
const MAP_ZOOM = 12; // zoom mais próximo sobre São Luís
const DATA_URL_CANDIDATES = [
  './data/points.json',       // produção (arquivo copiado para web/data)
  'data/points.json',         // produção alternativa
  '../data/points.json'       // desenvolvimento local (repo raiz)
];

function normalizeStatus(status) {
  const s = (status || '').toUpperCase().replace(/["'`]/g, '');
  const ascii = s.normalize('NFD').replace(/\p{Diacritic}/gu, '');
  if (ascii.includes('IMPROPRIO') || ascii.includes('IMPRPRIO')) return 'IMPRÓPRIO';
  if (ascii.includes('PROPRIO')) return 'PRÓPRIO';
  return 'DESCONHECIDO';
}

function statusColor(status) {
  const n = normalizeStatus(status);
  if (n === 'PRÓPRIO') return '#16a34a';
  if (n === 'IMPRÓPRIO') return '#dc2626';
  return '#6b7280';
}

function statusTag(status) {
  const n = normalizeStatus(status);
  if (n === 'PRÓPRIO') return { cls: 'green', label: 'PRÓPRIO' };
  if (n === 'IMPRÓPRIO') return { cls: 'red', label: 'IMPRÓPRIO' };
  return { cls: 'gray', label: 'DESCONHECIDO' };
}

function renderPopup(p) {
  const latest = p.latest || {};
  const tag = statusTag(latest.status);
  const hist = (p.history || [])
    .slice()
    .sort((a, b) => (a.date < b.date ? 1 : -1));

  const histHtml = hist
    .slice(0, 6)
    .map(h => `${h.date} - ${normalizeStatus(h.status)}`)
    .join('<br/>');

  const preferredSource = (() => {
    const s = p.source_laudo || '';
    if (typeof s === 'string' && s.startsWith('http')) return s;
    return 'https://www.sema.ma.gov.br/laudos-de-balneabilidade';
  })();
  const srcLink = `<div class="muted">Fonte: <a href="${preferredSource}" target="_blank" rel="noreferrer">SEMA/MA</a></div>`;

  const refClean = (() => {
    const r = (p.reference || '').trim();
    if (/^\d{1,3}$/.test(r)) return '';
    return r;
  })();

  return `
    <div class="popup">
      <h3>${p.code} – ${p.beach || 'Praia'}</h3>
      <div class="muted">${refClean}</div>
      <div class="status" style="margin-top:6px;">
        Coleta: ${latest.date || '-'}
        <span class="tag ${tag.cls}">${tag.label}</span>
      </div>
      ${histHtml ? `<div class="history"><strong>Série histórica:</strong><br/>${histHtml}</div>` : ''}
      ${srcLink}
    </div>
  `;
}

async function loadData() {
  let lastErr = null;
  for (const url of DATA_URL_CANDIDATES) {
    try {
      const resp = await fetch(url, { cache: 'no-store' });
      if (resp.ok) return await resp.json();
      lastErr = new Error(`HTTP ${resp.status} em ${url}`);
    } catch (e) { lastErr = e; }
  }
  throw lastErr || new Error('Falha ao carregar dados.');
}

async function main() {
  const map = L.map('map').setView(MAP_CENTER, MAP_ZOOM);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18,
    attribution: '&copy; OpenStreetMap contributors'
  }).addTo(map);

  let data = [];
  try {
    data = await loadData();
  } catch (e) {
    console.error(e);
  }

  data
    .filter(p => typeof p.lat === 'number' && typeof p.lng === 'number')
    .forEach(p => {
      const color = statusColor(p.latest?.status);
      const marker = L.circleMarker([p.lat, p.lng], {
        radius: 8,
        color,
        weight: 2,
        fillColor: color,
        fillOpacity: 0.35
      });
      marker.bindPopup(renderPopup(p));
      marker.addTo(map);
    });
}

main();
