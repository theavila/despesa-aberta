# Projeto: Serenata — transparência automatizada dos gastos públicos

## Contexto
Inspirado na Operação Serenata de Amor (robô Rosie + painel Jarbas). Quero uma versão
moderna: um pipeline que coleta despesas oficiais de parlamentares federais, detecta
gastos atípicos com regras transparentes, publica automaticamente nas redes sociais e
mantém um site com aparência de jornal como repositório público de tudo.

Trabalhe em etapas. Ao fim de cada etapa: rode os testes, faça commit com mensagem
no padrão Conventional Commits (em português) e me mostre um resumo curto.
Não avance se os testes falharem.

## Princípio editorial (inegociável)
- Imparcialidade: as mesmas regras, os mesmos limites e o mesmo modelo de texto valem
  para todos os parlamentares, partidos e estados. Nenhuma regra pode usar partido,
  ideologia ou nome como critério.
- Linguagem factual e sem adjetivos. Nunca "escândalo", "absurdo", "roubo".
  Um alerta é um "gasto atípico segundo a regra X", nunca uma acusação.
- Todo alerta mostra: valor, data, fornecedor (CNPJ), regra que disparou, explicação
  da regra em linguagem simples e link para o documento oficial.
- Todo post e toda página trazem o aviso: "Atipicidade estatística não é prova de
  irregularidade. O parlamentar pode ter justificativa."
- Página "Direito de resposta" e campo para registrar justificativas recebidas.
- Página "Metodologia" pública com todas as regras e o código-fonte delas.

## Stack
- Python 3.12 gerenciado com `uv`; `httpx`, `polars`, `duckdb`, `pydantic`, `pytest`, `ruff`.
- Banco: DuckDB em arquivo (`data/serenata.duckdb`) na v1.
- Site: Astro (estático), gerado a partir de JSONs exportados pelo pipeline,
  publicado no GitHub Pages.
- Automação: GitHub Actions (cron) para coleta diária e disparos.
- Segredos sempre via variáveis de ambiente / GitHub Secrets; criar `.env.example`,
  nunca commitar `.env`.

## Estrutura de pastas
```
serenata-nova/
├── pipeline/
│   ├── coletores/      # camara.py, senado.py
│   ├── normalizacao/   # esquema único de despesa
│   ├── regras/         # uma regra por arquivo, cada uma com teste
│   ├── publicadores/   # x.py, bluesky.py, mastodon.py, base.py
│   ├── exportar.py     # gera JSONs para o site
│   └── cli.py          # comandos: coletar, analisar, publicar, exportar
├── site/               # projeto Astro
├── tests/
├── data/               # ignorado no git, exceto amostras em tests/fixtures
├── .github/workflows/
└── docs/metodologia.md
```

## Etapa 1 — Coleta
- Câmara: baixar `https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip` (CSV `;`, UTF-8).
  Dados dos deputados: `https://dadosabertos.camara.leg.br/api/v2/deputados`.
  Ligar despesa ao deputado por `ideCadastro` (= id da API).
- Senado: `https://www.senado.leg.br/transparencia/LAI/verba/despesa_ceaps_{ano}.csv`.
  Atenção: Latin-1, separador `;`, vírgula decimal, PRIMEIRA LINHA É METADADO.
  Senador identificado por nome: ligar à lista oficial por nome normalizado
  (maiúsculas, sem acento). Lista: `https://legis.senado.leg.br/dadosabertos/senador/lista/atual`.
- Coleta incremental e idempotente (hash por linha para não duplicar).
- Retry com backoff exponencial, timeout, User-Agent identificando o projeto.
- Testes com fixtures pequenas (20 linhas de cada fonte) — sem rede nos testes.

## Etapa 2 — Normalização
Esquema único `Despesa`: id, casa (camara|senado), parlamentar_id, parlamentar_nome,
partido, uf, data, competencia, categoria, fornecedor_nome, fornecedor_cnpj_cpf,
valor, url_documento, fonte, coletado_em.

## Etapa 3 — Regras de atipicidade (determinísticas, explicáveis)
Cada regra: id, nome, descrição em linguagem simples, função pura, teste.
1. `R01_refeicao_alta`: refeição individual acima de um limite configurável.
2. `R02_duplicidade`: mesmo fornecedor, mesmo valor, mesma data, mesmo parlamentar.
3. `R03_outlier_categoria`: valor acima do percentil 99 da categoria no ano.
4. `R04_cnpj_situacao`: fornecedor com CNPJ inativo ou aberto depois da data da
   despesa (consultar BrasilAPI `/api/cnpj/v1/{cnpj}`, com cache local e limite de taxa).
5. `R05_fim_de_semana`: despesa de categorias de expediente em sábado/domingo/feriado.
Gerar uma tabela `alertas` com score e referência à regra. Limites em `config.toml`.

## Etapa 4 — Publicadores
- Interface `Publicador` com `publicar(alerta) -> resultado` e modo `--dry-run`
  (padrão: dry-run ligado; só publica de verdade com `PUBLICAR=1`).
- X: API v2 `POST /2/tweets` com OAuth 1.0a (user context). NÃO incluir link no
  texto (posts com link têm tarifa muito mais alta); usar o código do alerta, ex.
  "Busque A-2026-00123 no site".
- Bluesky: biblioteca `atproto`, com link e card.
- Mastodon: biblioteca `Mastodon.py`, com link.
- Modelo de texto único e neutro para todos, ex.:
  "[Câmara] Dep. {nome} ({partido}-{uf}) — R$ {valor} em {categoria}, {data},
   fornecedor {fornecedor}. Regra: {regra_nome}. Atípico ≠ irregular. Cód. {codigo}"
- Controle: limite de N posts por dia por rede, nunca repetir alerta já publicado,
  fila ordenada por score, log de cada publicação no banco.

## Etapa 5 — Site com aparência de jornal
- Visual de jornal impresso moderno: logotipo-título serifado no topo, data por
  extenso, colunas, filetes finos separando seções, manchete e "linha fina",
  tipografia serifada para títulos (ex. Playfair Display / Source Serif) e sans para
  dados (ex. Inter), papel creme claro, tinta quase preta, um único tom de destaque.
  Sem cores partidárias (nada de vermelho/azul/verde/amarelo associados a partidos).
- Responsivo, modo escuro, acessível (contraste AA, navegação por teclado).
- Páginas: Capa (alertas mais recentes como manchetes + números do dia),
  Alerta (detalhe completo + link oficial + regra + espaço para resposta),
  Parlamentar (histórico, total por categoria, gráfico), Fornecedor,
  Busca (por código, nome, CNPJ, UF, partido — client-side com Pagefind),
  Metodologia, Direito de resposta, Sobre.
- Dinâmico: "Última atualização", contador do dia, ticker de últimos alertas,
  feed RSS/Atom, dados abertos para download (CSV/JSON) em cada página.
- Gerado a partir de `site/src/data/*.json` exportados pelo pipeline.

## Etapa 6 — Automação (GitHub Actions)
- `pipeline.yml`: cron diário (06:00 America/Sao_Paulo) → coletar → analisar →
  exportar → commit dos JSONs → build e deploy do site no GitHub Pages.
- `publicar.yml`: cron a cada 3 horas em horário comercial → publica até N alertas.
- `ci.yml`: ruff + pytest + build do site em cada push/PR.
- Cache do DuckDB entre execuções (artifact ou branch `data`).

## Etapa 7 — Documentação
README em português: o que é, como rodar local, como configurar segredos,
metodologia resumida, licença (MIT para código, ODbL para dados), como contribuir.

## Critério de "v1 funcional"
`uv run serenata coletar --ano 2026 && uv run serenata analisar && uv run serenata exportar`
roda local; `npm run build` em `site/` gera o site; `uv run serenata publicar --dry-run`
mostra os posts que seriam enviados; os workflows passam no GitHub.