#!/bin/bash
#
# Script helper para processar PDF de laudo baixado manualmente
#
# Uso:
#   ./etl/process_manual_pdf.sh <caminho-do-pdf> [url-do-pdf-original]
#
# Exemplo:
#   ./etl/process_manual_pdf.sh ~/Downloads/Laudo_de_Balneabilidade_02_02_2026.pdf \
#     https://sema.ma.gov.br/uploads/sema/docs/Laudo_de_Balneabilidade_02_02_2026.pdf
#

set -e

if [ -z "$1" ]; then
    echo "Erro: Forneça o caminho do PDF baixado"
    echo ""
    echo "Uso: $0 <caminho-do-pdf> [url-original-opcional]"
    echo ""
    echo "Exemplo:"
    echo "  $0 ~/Downloads/Laudo_de_Balneabilidade_02_02_2026.pdf"
    echo ""
    echo "Ou com URL original:"
    echo "  $0 ~/Downloads/Laudo_de_Balneabilidade_02_02_2026.pdf \\"
    echo "     https://sema.ma.gov.br/uploads/sema/docs/Laudo_de_Balneabilidade_02_02_2026.pdf"
    exit 1
fi

PDF_PATH="$1"
PDF_URL="${2:-https://sema.ma.gov.br/laudos-de-balneabilidade}"

if [ ! -f "$PDF_PATH" ]; then
    echo "Erro: Arquivo não encontrado: $PDF_PATH"
    exit 1
fi

echo "=============================================="
echo "Processando PDF de Laudo de Balneabilidade"
echo "=============================================="
echo ""
echo "PDF local: $PDF_PATH"
echo "URL fonte: $PDF_URL"
echo ""

# Copia o PDF para data/raw/
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RAW_DIR="$PROJECT_ROOT/data/raw"

mkdir -p "$RAW_DIR"

PDF_FILENAME=$(basename "$PDF_PATH")
DEST_PATH="$RAW_DIR/$PDF_FILENAME"

echo "Copiando PDF para $DEST_PATH..."
cp "$PDF_PATH" "$DEST_PATH"

echo ""
echo "Executando ETL..."
echo ""

cd "$PROJECT_ROOT"
python etl/fetch_sema.py \
    --from-file "$DEST_PATH" \
    --web-source-url "$PDF_URL"

echo ""
echo "=============================================="
echo "Processamento concluído!"
echo "=============================================="
echo ""
echo "Verifique os resultados em:"
echo "  - data/points.json (dados para o mapa)"
echo "  - data/stations_index.csv (índice de estações)"
echo ""
