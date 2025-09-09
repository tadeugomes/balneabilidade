# Mapa de Balneabilidade – Maranhão (protótipo)

Protótipo de um mapa em Leaflet para exibir o status de balneabilidade dos pontos monitorados (SEMA/MA), com esqueleto de ETL para baixar e extrair dados dos PDFs.

## Como usar (rápido)

1) Servir estáticos na raiz do repositório (exemplos):

- Python: `python -m http.server 8000`
- Node: `npx serve -p 8000`

2) Abrir `http://localhost:8000/web/index.html`.

O mapa carrega `data/points.json`. Já existe um exemplo (P19) para validar a visualização.

## Pipeline de dados (ETL)

- `etl/fetch_sema.py`: esqueleto para:
  - Indexar laudos em `https://www.sema.ma.gov.br/laudos-de-balneabilidade`;
  - Baixar PDFs para `data/raw/`;
  - Extrair pontos (código, praia, referência), datas e status;
  - Consolidar histórico por ponto e gerar `data/points.json`.
  - Gera também `data/stations_index.csv` com a lista de pontos detectados (facilita preencher coordenadas).

- `data/stations_geocoded.csv`: tabela de geocódigos por ponto (manual inicialmente). O ETL usa este arquivo para lat/lng. Inclui um exemplo. Atualize com coordenadas corretas.

## Estrutura

- `web/index.html`: página do mapa (Leaflet)
- `web/app.js`: lógica do mapa e popups
- `web/styles.css`: estilos básicos e legenda
- `data/points.json`: dados (exemplo e saída do ETL)
- `etl/fetch_sema.py`: esqueleto do coletor e parser

## Próximos passos sugeridos

1. Completar o parser de PDF conforme o layout real (ajustar regex e extração de tabela por página).  
2. Preencher `data/stations_geocoded.csv` com coordenadas oficiais dos pontos (uma só vez).  
3. Automatizar atualização semanal (GitHub Actions/Cron) para baixar novo laudo e atualizar `data/points.json`.  
4. Adicionar camada de filtros (cidade/praia/status) e legenda mais rica.  
5. Publicar via GitHub Pages ou Netlify (direto da pasta raiz).

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
