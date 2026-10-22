# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Estado atual

O repositório ainda está vazio: só há `PROMPT.md` (a especificação completa do projeto) e um `README.md` provisório. **`PROMPT.md` é a fonte da verdade** — leia-o antes de qualquer etapa. A raiz deste repositório corresponde à pasta `serenata-nova/` da estrutura descrita lá. Atualize este arquivo à medida que o código real substituir o planejado.

Obs.: o `README.md` atual está em UTF-16 LE (o git o trata como binário); ao reescrevê-lo na Etapa 7, salve em UTF-8.

## Fluxo de trabalho exigido

- Trabalhar por etapas (1 Coleta → 2 Normalização → 3 Regras → 4 Publicadores → 5 Site → 6 Actions → 7 Docs).
- Ao fim de cada etapa: rodar testes, commitar em **Conventional Commits em português** (ex.: `feat: adiciona coletor da Câmara`) e mostrar um resumo curto.
- **Não avançar de etapa se os testes falharem.**
- Testes nunca acessam a rede: usar fixtures pequenas (~20 linhas por fonte) em `tests/fixtures/`.

## Comandos (planejados)

```bash
uv sync                                   # dependências Python 3.12
uv run ruff check . && uv run ruff format .
uv run pytest                             # todos os testes
uv run pytest tests/caminho/test_x.py::test_nome   # um teste
uv run serenata coletar --ano 2026
uv run serenata analisar
uv run serenata exportar                  # gera site/src/data/*.json
uv run serenata publicar --dry-run
cd site && npm run build                  # site Astro estático
```

Critério de "v1 funcional": a sequência coletar → analisar → exportar roda localmente, `npm run build` gera o site, `publicar --dry-run` mostra os posts e os workflows passam no GitHub.

## Arquitetura

Pipeline Python (`pipeline/`, CLI `serenata`) → DuckDB em arquivo (`data/serenata.duckdb`, fora do git) → JSONs exportados → site Astro estático (GitHub Pages). Publicadores em redes sociais leem a tabela `alertas`.

- **Coletores** (`pipeline/coletores/`): coleta incremental e idempotente (hash por linha), retry com backoff exponencial, timeout e User-Agent do projeto.
  - Câmara: `cotas/Ano-{ano}.csv.zip` (`;`, UTF-8); liga ao deputado via `ideCadastro` = id da API v2.
  - Senado: CEAPS CSV em **Latin-1, `;`, vírgula decimal e primeira linha de metadado**; senador identificado só por nome → casar com a lista oficial por nome normalizado (maiúsculas, sem acento).
- **Normalização**: esquema único `Despesa` (pydantic) com os campos listados na Etapa 2 do `PROMPT.md`; tudo a jusante consome só esse esquema.
- **Regras** (`pipeline/regras/`): uma regra por arquivo, função pura e determinística, com id, nome, descrição em linguagem simples e teste próprio. Limites em `config.toml`. Saída: tabela `alertas` com score e referência à regra. R04 consulta a BrasilAPI com cache local e limite de taxa.
- **Publicadores** (`pipeline/publicadores/`): interface `Publicador.publicar(alerta)`; **dry-run é o padrão**, só publica de verdade com `PUBLICAR=1`. Um único modelo de texto para todas as redes; X sem link no texto (usar código do alerta, ex. `A-2026-00123`); Bluesky e Mastodon com link. Limite diário por rede, nunca repetir alerta, fila por score, log no banco.
- **Site** (`site/`): Astro gerado a partir de `site/src/data/*.json`; busca client-side com Pagefind; RSS/Atom e downloads CSV/JSON. Visual de jornal (serifada nos títulos, sans nos dados, papel creme, um único tom de destaque) — **sem cores associadas a partidos** (vermelho/azul/verde/amarelo).
- **Automação**: `pipeline.yml` (diário 06:00 America/Sao_Paulo, cache do DuckDB entre execuções), `publicar.yml` (a cada 3h em horário comercial), `ci.yml` (ruff + pytest + build do site).
- Segredos só via env / GitHub Secrets; manter `.env.example` atualizado.

## Princípio editorial (inegociável — vale para código, textos e site)

- Mesmas regras, limites e modelo de texto para todos. **Nenhuma regra pode usar partido, ideologia ou nome como critério.**
- Linguagem factual, sem adjetivos: um alerta é "gasto atípico segundo a regra X", nunca acusação ("escândalo", "absurdo", "roubo" são proibidos).
- Todo alerta exibe valor, data, fornecedor (CNPJ), regra, explicação simples e link para o documento oficial.
- Todo post e toda página trazem: "Atipicidade estatística não é prova de irregularidade. O parlamentar pode ter justificativa."
- Manter páginas "Metodologia" (regras + código-fonte) e "Direito de resposta" (com registro de justificativas).
