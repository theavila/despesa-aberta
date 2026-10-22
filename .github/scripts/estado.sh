#!/usr/bin/env bash
# Sincroniza a pasta `estado/` (Parquet de alertas, publicações e cache de CNPJ) com o
# branch `data`. Uso: estado.sh baixar | enviar "<mensagem de commit>"
set -euo pipefail

PASTA="${PASTA_ESTADO:-estado}"
RAMO="${RAMO_ESTADO:-data}"

case "${1:-}" in
  baixar)
    mkdir -p "$PASTA"
    if git fetch --depth=1 origin "$RAMO" 2>/dev/null; then
      git archive FETCH_HEAD | tar -x -C "$PASTA"
      echo "Estado restaurado do branch $RAMO: $(ls "$PASTA" | tr '\n' ' ')"
    else
      echo "Branch $RAMO ainda não existe; começando sem estado."
    fi
    ;;
  enviar)
    mensagem="${2:-chore(dados): atualiza estado}"
    destino="$(mktemp -d)"
    if git fetch --depth=1 origin "$RAMO" 2>/dev/null; then
      git worktree add --detach "$destino" FETCH_HEAD
    else
      git worktree add --detach "$destino"
      git -C "$destino" checkout --orphan "$RAMO-novo"
      git -C "$destino" rm -rf --quiet --ignore-unmatch .
    fi
    cp "$PASTA"/*.parquet "$destino"/
    git -C "$destino" add -A
    if git -C "$destino" diff --cached --quiet; then
      echo "Estado sem mudanças."
    else
      git -C "$destino" commit --quiet -m "$mensagem"
      git -C "$destino" push --quiet origin "HEAD:refs/heads/$RAMO"
      echo "Estado enviado para o branch $RAMO."
    fi
    git worktree remove --force "$destino"
    ;;
  *)
    echo "uso: $0 baixar | enviar \"mensagem\"" >&2
    exit 2
    ;;
esac
