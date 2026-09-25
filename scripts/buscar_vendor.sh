#!/usr/bin/env bash
#
# Baixa o Chart.js para static/vendor/.
#
# O arquivo já vem versionado no repositório, então isso só é necessário para
# trocar de versão: ajuste VERSAO abaixo e rode. Servir a biblioteca do próprio
# Raspberry, em vez de um CDN, mantém o dashboard funcionando numa rede local
# sem internet.
#
#   ./scripts/buscar_vendor.sh

set -euo pipefail

VERSAO="4.4.7"
DESTINO="$(dirname "$0")/../static/vendor/chart.umd.min.js"
URL="https://cdn.jsdelivr.net/npm/chart.js@${VERSAO}/dist/chart.umd.min.js"

echo "Baixando Chart.js ${VERSAO}..."
curl -fsSL "$URL" -o "$DESTINO"

echo "Pronto: $(cd "$(dirname "$DESTINO")" && pwd)/$(basename "$DESTINO")"
