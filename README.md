# Despesa Aberta

Transparência automatizada dos gastos de deputados e senadores federais.

Todos os dias, um robô baixa as despesas oficiais da cota parlamentar da Câmara e do
Senado e aplica regras públicas e determinísticas para encontrar gastos atípicos. Depois
publica os alertas nas redes sociais e mantém um site com aparência de jornal como arquivo
público de tudo. O projeto se inspira na Operação Serenata de Amor (a robô Rosie e o
painel Jarbas).

> **Atipicidade estatística não é prova de irregularidade. O parlamentar pode ter
> justificativa.**

## Princípio editorial

- **As mesmas regras, os mesmos limites e o mesmo texto valem para todos.** Nenhuma regra
  usa partido, ideologia ou nome. Há um teste automático que garante isso.
- **Linguagem factual.** Um alerta é um "gasto atípico segundo a regra X", nunca uma
  acusação.
- **Todo alerta mostra** o valor, a data, o fornecedor (CNPJ), a regra que disparou, a
  explicação da regra em linguagem simples e o link para o documento oficial.
- **Direito de resposta:** quem é citado pode enviar uma justificativa, publicada na
  íntegra ao lado do alerta.
- **Metodologia pública:** o site traz todas as regras, seus parâmetros e o código-fonte.

## Como funciona

```
Câmara (CEAP) ─┐                          ┌─► site (Astro, GitHub Pages)
               ├─► coletar ─► normalizar ─► analisar ─► exportar
Senado (CEAPS)─┘      │                        │
                      ▼                        ▼
                  DuckDB (data/despesa-aberta.duckdb) ─► publicar ─► X, Bluesky, Mastodon
```

| Etapa | Comando | O que faz |
|---|---|---|
| Coleta | `despesa-aberta coletar` | Baixa os arquivos do ano, com retry e um hash por linha (idempotente). Liga deputados pelo `ideCadastro` e senadores pelo nome normalizado. |
| Normalização | (ao fim da coleta) | Converte tudo para o esquema único `Despesa`. |
| Análise | `despesa-aberta analisar` | Aplica as regras R01 a R05 e mantém a tabela `alertas` com códigos estáveis (`A-2026-00123`). |
| Exportação | `despesa-aberta exportar` | Gera `site/src/data/*.json`. |
| Publicação | `despesa-aberta publicar` | Posta os alertas de maior pontuação, respeitando um limite diário por rede. **Dry-run por padrão.** |

A documentação técnica completa (arquitetura, modelo de dados, ciclo de vida dos alertas,
operação) está em [docs/sistema.md](docs/sistema.md). As regras estão resumidas em
[docs/metodologia.md](docs/metodologia.md). Os limites e
pesos ficam em [`config.toml`](config.toml).

## Como rodar localmente

Requisitos: [uv](https://docs.astral.sh/uv/) (o Python 3.12 vem junto) e Node.js 24.

```bash
uv sync

# v1: coleta 2026, analisa e exporta para o site
uv run despesa-aberta coletar --ano 2026
uv run despesa-aberta analisar
uv run despesa-aberta exportar

# Mostra os posts que seriam enviados (nada é publicado)
uv run despesa-aberta publicar --dry-run

# Site
cd site
npm ci
npm run build      # gera site/dist com o índice de busca (Pagefind)
npm run preview    # http://localhost:4321/despesa-aberta/
```

Outros comandos úteis:

```bash
uv run despesa-aberta analisar --sem-cnpj        # não consulta a BrasilAPI (usa só o cache)
uv run despesa-aberta publicar --rede bluesky --limite 1
uv run despesa-aberta resposta --alerta A-2026-00123 --autor "Gabinete do parlamentar" --arquivo resposta.txt
uv run despesa-aberta estado salvar|restaurar    # alertas, publicações e cache de CNPJ em Parquet
```

Testes e lint:

```bash
uv run pytest
uv run pytest tests/regras/test_r02_duplicidade.py::test_marca_repeticoes_mas_nao_a_primeira
uv run ruff check . && uv run ruff format --check .
```

Os testes não acessam a rede. Usam fixtures pequenas, com 20 linhas reais de cada
fonte, em `tests/fixtures/`.

## Configurar segredos

Copie `.env.example` para `.env` (que nunca vai para o git) e preencha só o que for usar.

| Variável | Para quê |
|---|---|
| `PUBLICAR` | `1` publica de verdade; qualquer outro valor mantém o dry-run |
| `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET` | X, API v2 com OAuth 1.0a (user context) |
| `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD` | Bluesky (use uma senha de app) |
| `MASTODON_API_BASE_URL`, `MASTODON_ACCESS_TOKEN` | Mastodon |

No GitHub, cadastre as credenciais em *Settings → Secrets and variables → Actions*:

- **Secrets:** `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`,
  `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD`, `MASTODON_ACCESS_TOKEN`.
- **Variables:** `MASTODON_API_BASE_URL` e `PUBLICAR`. Deixe `PUBLICAR` sem valor até
  conferir os posts no log do workflow; depois, defina `1`.

Em *Settings → Pages*, escolha **GitHub Actions** como fonte.

## Automação (GitHub Actions)

- `ci.yml`: ruff, pytest e build do site em cada push e PR.
- `pipeline.yml`: todo dia às 06:00 (Brasília), coleta, analisa, exporta, faz commit dos
  JSONs e publica o site. Roda também quando um push altera o pipeline, a configuração,
  as respostas ou o site.
- `publicar.yml`: nos dias úteis, às 09h, 12h, 15h e 18h, publica até
  `publicacao.por_execucao` alertas por rede.

As despesas são baixadas de novo a cada execução. Já os códigos dos alertas, o log de
publicações e o cache de CNPJ ficam em Parquet no branch `data`. O histórico desse branch
serve de trilha de auditoria do que foi publicado.

## Direito de resposta

As justificativas chegam pelo formulário de issue "Direito de resposta" e são registradas
com `despesa-aberta resposta`. O comando grava um arquivo em `respostas/<código>-<n>.toml`, e
ele entra no site na próxima execução do pipeline.

## Como contribuir

- Abra uma issue antes de propor uma regra nova. Toda regra precisa ser determinística e
  explicável em linguagem simples, e não pode usar partido, ideologia ou nome como
  critério.
- Cada regra fica em `pipeline/regras/rNN_nome.py`: uma função pura `aplicar`, com
  `REGRA` (id, nome e descrição), parâmetros em `config.toml` e um teste em
  `tests/regras/`.
- Rode `uv run pytest` e `uv run ruff check .` antes do PR. Mensagens de commit seguem o
  [Conventional Commits](https://www.conventionalcommits.org/pt-br/), em português.

## Licença

- Código: [MIT](LICENSE).
- Dados derivados (alertas e JSONs do site): [Open Database License (ODbL) 1.0](LICENSE-DADOS.md).
  Os dados originais são publicados pela Câmara dos Deputados e pelo Senado Federal.
