# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Projeto **Despesa Aberta** (nome anterior: Serenata, ainda usado em `PROMPT.md`): coleta despesas da cota parlamentar (Câmara e Senado), marca gastos atípicos com regras públicas, publica nas redes e gera um site estático com cara de jornal. A especificação original está em `PROMPT.md`; o README descreve uso e configuração; `docs/sistema.md` é a documentação técnica (mantenha-a atualizada ao mudar tabelas, comandos, rotas ou workflows).

## Comandos

```bash
uv sync
uv run pytest                                   # todos os testes (sem rede)
uv run pytest tests/regras/test_r01_refeicao_alta.py::test_marca_refeicao_acima_do_limite
uv run ruff check . && uv run ruff format --check .

uv run despesa-aberta coletar [--ano 2026]            # baixa + normaliza (tabela despesas)
uv run despesa-aberta analisar [--sem-cnpj]           # regras -> tabela alertas (consulta BrasilAPI sem a flag)
uv run despesa-aberta exportar                        # site/src/data/*.json
uv run despesa-aberta publicar --dry-run              # dry-run é o padrão; real só com PUBLICAR=1
uv run despesa-aberta estado salvar|restaurar         # Parquet do estado persistente (pasta estado/)

cd site && npm ci && npm run build              # astro build + pagefind; preview em /despesa-aberta/
```

## Arquitetura

Fluxo: `coletores/` → tabela `bruto` (JSON por linha, PK = hash) → `normalizacao/` reconstrói `despesas` inteira a partir de `bruto` → `regras/` + `analise.py` → `alertas` → `exportar.py` (JSONs do site) e `publicacao.py` (redes). Tudo em DuckDB (`data/despesa-aberta.duckdb`, fora do git); esquema em `pipeline/db.py`.

- **Ids estáveis são a espinha do sistema.** `despesas.id` é o hash SHA-256 da linha da fonte (`coletores/base.py:adicionar_hash`); os alertas referenciam esse id. Mudar a fórmula do hash ou as colunas lidas invalida todos os alertas e códigos.
- **Códigos de alerta** (`A-{ano da competência}-{seq}`) são atribuídos em `analise.gravar_alertas` por (regra_id, despesa_id), nunca reutilizados; alertas que deixam de disparar viram `ativo = false`.
- **Regras**: um arquivo por regra em `pipeline/regras/rNN_*.py`, exportando `REGRA` (id, nome, descrição em linguagem simples, `aplicar`). `aplicar(despesas, params, contexto)` é pura e devolve `despesa_id, intensidade (0–1), detalhe`; score = round(100 × peso × intensidade). Parâmetros em `config.toml` `[regras.<id>]` — `tests/test_analise.py` exige que config e registro (`regras/__init__.py:REGRAS`) batam. Categorias são comparadas via `normalizar_nome` (sem acento/caixa).
- **Estado persistente no CI**: despesas são rebaixadas a cada execução; só `alertas`, `publicacoes` e `cnpj_cache` vão para o branch `data` em Parquet (`pipeline/estado.py` + `.github/scripts/estado.sh`). Os workflows `pipeline.yml` e `publicar.yml` compartilham o grupo de concorrência `despesa-aberta-estado`.
- **Publicadores** (`pipeline/publicadores/`): subclasses de `Publicador` com `sufixo`, `tamanho`, `configurado`, `enviar`. O texto base é único (`base.texto_base`); X não pode ter link (OAuth 1.0a assinado à mão em `x.py`). `atproto` e `mastodon` são importados dentro de `enviar`.
- **Site** (`site/`, Astro 7): lê os JSONs via `src/lib/dados.ts` (fs, a partir de `process.cwd()`). Sempre monte links com `url()`/`urlAlerta()` etc., pois o site roda sob `base` (`/despesa-aberta`, ou `BASE_PATH`). Downloads CSV/JSON são endpoints `*.json.ts`/`*.csv.ts`. Só páginas com `data-pagefind-body` (alerta, parlamentar, fornecedor) entram na busca.
- **Direito de resposta**: arquivos `respostas/<código>-<n>.toml` (versionados), lidos no `exportar`.

## Armadilhas

- DuckDB 2.x: use `db.consultar()` (→ polars) e `db.escalar()`; `con.execute(...).fetchone()` deixa resultado pendente e quebra a próxima chamada, e `.pl()` não existe no resultado de `execute`.
- polars 2.x: `read_csv(..., empty_string_is_null=False)`; leia CSV sempre como texto (`infer_schema=False`) e converta na normalização.
- O CSV da Câmara é UTF-8 com BOM (não Latin-1); o do Senado é Latin-1 com uma linha de metadado antes do cabeçalho.
- No Windows, saída do CLI precisa de UTF-8 (já tratado em `cli.main`); para scripts avulsos use `PYTHONIOENCODING=utf-8`.

## Princípio editorial (inegociável)

Mesmas regras, limites e texto para todos; nenhuma regra pode usar partido, ideologia ou nome (há teste que embaralha esses campos). Linguagem factual: "gasto atípico segundo a regra X", nunca acusação nem adjetivos como "escândalo". Todo alerta mostra valor, data, fornecedor (CNPJ), regra, explicação simples e link oficial; toda página e post trazem o aviso "Atipicidade estatística não é prova de irregularidade. O parlamentar pode ter justificativa." Visual sem cores partidárias (um único destaque café, `--destaque`).

## Fluxo de trabalho

Commits em Conventional Commits, em português. Rode testes e ruff antes de commitar; não avance etapas com testes falhando.
