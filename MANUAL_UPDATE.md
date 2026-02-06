# Atualização Manual de Dados

Este guia explica como atualizar manualmente os dados de balneabilidade quando o scraping automático não está funcionando (por exemplo, quando o IP do servidor está bloqueado pela SEMA).

## 🚨 Quando usar este método

Use atualização manual quando:
- O scraping automático retorna erro 503 (Service Unavailable)
- Você está executando em um ambiente com IP bloqueado
- O servidor SEMA está temporariamente inacessível para automação

## 📥 Passo 1: Baixar o PDF manualmente

1. Acesse o site da SEMA: https://sema.ma.gov.br/laudos-de-balneabilidade

2. Baixe o PDF mais recente, por exemplo:
   - https://sema.ma.gov.br/uploads/sema/docs/Laudo_de_Balneabilidade_02_02_2026.pdf

3. Salve o arquivo em um local conhecido (ex: `~/Downloads/`)

## 🔧 Passo 2: Processar o PDF baixado

### Opção A: Usando o script helper (recomendado)

```bash
./etl/process_manual_pdf.sh ~/Downloads/Laudo_de_Balneabilidade_02_02_2026.pdf \
  https://sema.ma.gov.br/uploads/sema/docs/Laudo_de_Balneabilidade_02_02_2026.pdf
```

### Opção B: Usando o comando direto

```bash
python etl/fetch_sema.py \
  --from-file ~/Downloads/Laudo_de_Balneabilidade_02_02_2026.pdf \
  --web-source-url https://sema.ma.gov.br/uploads/sema/docs/Laudo_de_Balneabilidade_02_02_2026.pdf
```

## ✅ Passo 3: Verificar os resultados

Após o processamento, verifique:

```bash
# Ver quantos pontos foram processados
python3 -c "import json; data = json.load(open('data/points.json')); print(f'Total: {len(data)} pontos'); dates = [p.get('latest', {}).get('date') for p in data if p.get('latest')]; print(f'Última data: {max(dates) if dates else \"N/A\"}')"
```

## 📤 Passo 4: Commit e deploy

```bash
# Adicionar arquivos alterados
git add data/points.json data/stations_index.csv data/raw/

# Criar commit
git commit -m "chore(data): atualização manual de dados $(date +%Y-%m-%d)

Processado manualmente: Laudo_de_Balneabilidade_DD_MM_YYYY.pdf

https://claude.ai/code/session_01AnLkG9hWABovogAof77UTu"

# Push para o repositório
git push
```

## 🔍 Troubleshooting

### Erro: "ModuleNotFoundError: No module named 'pdfplumber'"

Instale as dependências:
```bash
pip install -r etl/requirements.txt
```

### Erro: "PDF não encontrado"

Verifique se o caminho do arquivo está correto:
```bash
ls -lh ~/Downloads/Laudo_de_Balneabilidade_*.pdf
```

### Nenhum dado extraído do PDF

Possíveis causas:
- PDF corrompido ou com formato diferente
- Mudanças no layout do PDF pela SEMA
- Verifique se o PDF abre corretamente em um leitor de PDF

Entre em contato com o maintainer se o problema persistir.

## 📊 Estrutura de dados gerada

Após o processamento, os seguintes arquivos são atualizados:

- **`data/points.json`**: Dados JSON para o mapa web
- **`data/stations_index.csv`**: Índice de estações detectadas
- **`data/raw/*.pdf`**: PDF processado (salvo para referência)

## 🔄 Retornando ao scraping automático

Quando o servidor SEMA voltar a permitir acesso automatizado:

```bash
# Teste o scraping
python etl/fetch_sema.py --limit 5 --timeout 60

# Se funcionar, o sistema voltará ao normal
```

O workflow do GitHub Actions (`update_deploy.yml`) continuará tentando automaticamente toda quinta-feira.

---

**Última atualização**: 06/02/2026
