# Mapa de Balneabilidade – Maranhão

Protótipo de um mapa em Leaflet para exibir o status de balneabilidade dos pontos monitorados (SEMA/MA), com esqueleto de ETL para baixar e extrair dados dos PDFs.

## Como usar (rápido)

1) Servir estáticos na raiz do repositório (exemplos):

- Python: `python -m http.server 8000`
- Node: `npx serve -p 8000`

2) Abrir `http://localhost:8000/web/index.html`.

O mapa carrega `data/points.json`. Já existe um exemplo (P19) para validar a visualização.

## Funcionalidades

- Mapa interativo (Leaflet) com marcadores por ponto (círculos coloridos pelo status).
- Popups com: código, praia/localização, referência, data da coleta, status canônico (PRÓPRIO/IMPRÓPRIO) e série histórica.
- Link da fonte exibido como “SEMA/MA” apontando para o laudo público (quando informado).
- Responsivo: layout e legenda adaptados para telas móveis (título compacto, legenda no topo direito, fontes ajustadas).
- Toggle de legenda no mobile: botão para mostrar/ocultar a legenda em telas pequenas.
- Pipeline automático semanal (GitHub Actions) para atualizar os dados e publicar no GitHub Pages.
- ETL robusto a falhas: mantém os dados atuais quando não há laudo novo ou quando o site está indisponível.

## Pipeline de dados (ETL)

- `etl/fetch_sema.py`: esqueleto para:
  - Indexar laudos em `https://www.sema.ma.gov.br/laudos-de-balneabilidade`;
  - Baixar PDFs para `data/raw/`;
  - Extrair pontos (código, praia, referência), datas e status;
  - Consolidar histórico por ponto e gerar `data/points.json`.
  - Gera também `data/stations_index.csv` com a lista de pontos detectados (facilita preencher coordenadas).

### Regras importantes do ETL

- Prioriza o PDF mais recente (heurística de data extraída de link/texto, ex.: `dd_mm_aaaa` ou `dd/mm/aaaa`).
- Apenas sobrescreve `data/points.json` se o conjunto novo tiver data mais recente do que a atual no arquivo.
- Normaliza o status extraído para “PRÓPRIO” ou “IMPRÓPRIO”.
- Se o download/parse falhar, mantém o `points.json` existente e o deploy segue normalmente.

- `data/stations_geocoded.csv`: tabela de geocódigos por ponto (manual inicialmente). O ETL usa este arquivo para lat/lng. Inclui um exemplo. Atualize com coordenadas corretas.

## Estrutura

- `web/index.html`: página do mapa (Leaflet)
- `web/app.js`: lógica do mapa e popups
- `web/styles.css`: estilos básicos e legenda
- `data/points.json`: dados (exemplo e saída do ETL)
- `etl/fetch_sema.py`: esqueleto do coletor e parser



## Deploy automático (GitHub Actions + Pages)

- Workflow criado em `.github/workflows/update_deploy.yml` que:
  - Roda manualmente (workflow_dispatch) e toda quinta às 12:00 (MA/BR, UTC-3 → 15:00 UTC);
  - Executa o ETL (`etl/fetch_sema.py`) e atualiza `data/points.json`;
  - Copia `data/points.json` para `web/data/points.json`;
  - Faz deploy do conteúdo de `web/` para o GitHub Pages.

- Para habilitar o Pages:
  - Vá em Settings → Pages → Build and deployment → Source: “GitHub Actions”.
  - Após o primeiro deploy, a página ficará disponível em `https://<seu-usuario>.github.io/<seu-repo>/`.

- Observação sobre horário: o cron usa UTC (`0 15 * * 4`), equivalente a 12:00 de quinta-feira em MA/BR (UTC-3). Ajuste se necessário.

## Funcionamento do App

- Frontend estático em `web/` consome os dados de `web/data/points.json` (copiado no workflow a partir de `data/points.json`).
- O mapa está centralizado na região de São Luís com zoom aproximado; você pode alterar `MAP_CENTER` e `MAP_ZOOM` em `web/app.js`.
- A cor dos marcadores é baseada no status: PRÓPRIO (verde), IMPRÓPRIO (vermelho), DESCONHECIDO (cinza).
- A legenda flutua sobre o mapa; em telas pequenas, vai para o topo direito e tem fontes menores.
- O rodapé mostra o crédito do Observatório Portuário e a fonte institucional (SEMA/MA).

## Desenvolvimento local

- Servir estáticos: `python -m http.server 8000` e abrir `http://localhost:8000/web/index.html`.
- Atualizar dados manualmente (usando um PDF local e URL pública para a fonte):
  - `python etl/fetch_sema.py --from-file data/raw/SEU_LAUDO.pdf --web-source-url https://.../laudo.pdf`
- Atualizar coordenadas oficiais (CSV):
  - `python etl/import_official_coords.py --src caminho/do/oficial.csv`
  - Validar cobertura: `python etl/validate_geocodes.py`

## Esquema de dados (points.json)

- Estrutura por ponto:
  - `code`: código do ponto (ex.: P01)
  - `beach`, `reference`, `city`: metadados textuais
  - `lat`, `lng`: coordenadas decimais
  - `latest`: `{ date: AAAA-MM-DD, status: PRÓPRIO|IMPRÓPRIO }`
  - `history`: lista de `{ date, status }`
  - `source_laudo`: URL pública do laudo (quando disponível)

## Limitações conhecidas

- Layout dos PDFs pode variar, exigindo ajuste fino nas regex do parser (`etl/fetch_sema.py`).
- Eventuais acentuações estranhas podem aparecer no terminal do Windows, mas o navegador exibe corretamente.
- Se o site da SEMA mudar de estrutura de links/rotas, a indexação pode precisar adaptação.

## ETL – uso prático

- Instalar dependências (se o `python` for 3.13, ele instala `pip` automaticamente com `ensurepip`):
  - `python -m ensurepip --upgrade` (se precisar)
  - `python -m pip install -r etl/requirements.txt`

- Tentar baixar/parsear laudos mais recentes:
  - `python etl/fetch_sema.py --limit 5 --timeout 90`

- Se a página estiver indisponível ou lenta, usar um PDF local (coloque em `data/raw/`):
  - `python etl/fetch_sema.py --from-file data/raw/LAUDO_185-25.pdf`

- Após executar, conferir arquivos gerados:
  - `data/points.json` – consumido pelo mapa
  - `data/stations_index.csv` – lista de pontos detectados (para preencher coordenadas)

- Preencher coordenadas oficiais:
  - Edite `data/stations_geocoded.csv` e adicione/atualize `lat,lng` por `code`.
  - Rode novamente o ETL para refletir as coordenadas no `points.json`.
  - Alternativamente, importe um CSV oficial com `code,lat,lng` (ou `code,beach,reference,city,lat,lng`):
    - `python etl/import_official_coords.py --src caminho/do/oficial.csv`
  - Valide cobertura de coordenadas: `python etl/validate_geocodes.py`
