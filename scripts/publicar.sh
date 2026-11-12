#!/usr/bin/env bash
#
# Gera a cópia estática e publica no branch gh-pages.
#
#   scripts/publicar.sh
#
# O branch publicado tem SEMPRE um commit só. Cada publicação cria um
# repositório novo no diretório de build e dá push forçado, então o histórico
# não cresce: a cada 30 minutos seriam dezenas de megabytes por mês de HTML
# com os dados embutidos, e isso é o tipo de coisa que ninguém percebe até o
# clone começar a demorar.
#
# Como consequência, o que foi publicado antes não fica guardado. É
# intencional: o histórico dos dados está no banco, no aparelho. Isto aqui é
# uma vitrine, não um arquivo.
#
# Precisa de uma chave de deploy com escrita, configurada no GitHub, e do
# remoto por SSH. Com o remoto HTTPS o push pede senha e o timer trava.

set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTO="${MONITOR_REMOTO_PAGES:-git@github.com:LucasFASouza/monitor-ambiental.git}"
BRANCH="${MONITOR_BRANCH_PAGES:-gh-pages}"
BUILD="$(mktemp -d)"

limpar() { rm -rf "$BUILD"; }
trap limpar EXIT

cd "$RAIZ"

# A geração falha alto se algum template mudou de forma: melhor não publicar
# do que publicar uma página quebrada.
"${MONITOR_PYTHON:-$RAIZ/.venv/bin/python}" scripts/publicar.py --saida "$BUILD/site"

cd "$BUILD/site"
git init -q
git add -A
git -c user.name="monitor-ambiental" \
    -c user.email="monitor@localhost" \
    commit -q -m "Snapshot de $(date '+%d/%m/%Y às %Hh%M')"

git push --force --quiet "$REMOTO" "HEAD:$BRANCH"

echo "Publicado em $BRANCH: $(du -sh . | cut -f1)"
