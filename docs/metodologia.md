# Metodologia

A versão completa, com o código-fonte de cada regra, está na página **Metodologia** do
site. Ela é gerada a partir do próprio código, então nunca fica desatualizada.

## Fontes

| Casa | Arquivo | Particularidades |
|---|---|---|
| Câmara | `https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip` | CSV com `;`, UTF-8 com BOM. O deputado é identificado por `ideCadastro`, que é o id da API `dadosabertos.camara.leg.br/api/v2/deputados`. |
| Senado | `https://www.senado.leg.br/transparencia/LAI/verba/despesa_ceaps_{ano}.csv` | Latin-1, `;`, vírgula decimal, e a **primeira linha é metadado**. O senador vem só pelo nome. |

**Vínculo dos senadores.** Primeiro, compara-se o nome normalizado (maiúsculas, sem
acento) com a lista atual do Senado e, em seguida, com as listas das legislaturas do ano.
Se nada casar, procura-se o único senador cujo nome completo contém todas as palavras do
nome do CSV. Sem correspondência única, a despesa recebe um id derivado do nome
(`nome:<NOME>`).

**Coleta incremental e idempotente.** Cada linha recebe um hash SHA-256 de todos os seus
campos. Linhas idênticas no mesmo arquivo recebem também o número da ocorrência.

**Exclusões.** Despesas de lideranças e órgãos da Câmara (sem `ideCadastro`) ficam de fora.

**Valor.** Na Câmara usa-se o valor líquido (`vlrLiquido`); no Senado, o valor
reembolsado.

**Link oficial.** Na Câmara, é o documento fiscal; quando não há, a página do deputado. No
Senado, que não publica um link por documento, é a página de transparência do senador no
ano.

## Regras

Os limites e pesos estão em `config.toml` e são iguais para todos.

| Id | Nome | Dispara quando | Intensidade |
|---|---|---|---|
| R01_refeicao_alta | Refeição acima do limite | A refeição do parlamentar passa de R$ 250. Só vale para a Câmara: o Senado publica alimentação junto com locomoção e hospedagem. | valor ÷ limite, com teto em 5, ÷ 5 |
| R02_duplicidade | Possível duplicidade | Há mesmo parlamentar, fornecedor, valor e data de outra despesa. A primeira do grupo não é marcada. Mínimo de R$ 100. Hospedagem fica de fora (várias diárias na mesma noite são comuns). | 1 |
| R03_outlier_categoria | Valor muito acima do comum na categoria | O valor passa do percentil 99 da categoria no ano, entre todos os parlamentares. Exige pelo menos 100 despesas na categoria. | valor ÷ percentil, com teto em 5, ÷ 5 |
| R04_cnpj_situacao | Fornecedor com CNPJ irregular na data | Na data da despesa, a empresa ainda não existia ou já não estava ativa, segundo a Receita Federal (via BrasilAPI). | 1 |
| R05_fim_de_semana | Despesa de expediente em fim de semana ou feriado | Uma despesa de categoria de escritório tem documento emitido num sábado, domingo ou feriado nacional. Mínimo de R$ 100. | 1 |

**Pontuação** = 100 × peso da regra × intensidade. Ela serve só para ordenar a fila de
publicação e não mede gravidade.

**R04 e a BrasilAPI.** A consulta tem cache local de 90 dias e faz no máximo 1 consulta
por segundo e 300 por execução. A prioridade é dos fornecedores que mais receberam.
Despesas cujo CNPJ ainda não foi consultado não são avaliadas por esta regra.

**Feriados nacionais** (R05): 1º de janeiro, Sexta-feira Santa, 21 de abril, 1º de maio,
7 de setembro, 12 de outubro, 2 e 15 de novembro, 20 de novembro (desde 2024) e 25 de
dezembro.

## Códigos dos alertas

Cada par (regra, despesa) recebe um código `A-{ano da competência}-{sequência}`, que
nunca é reutilizado. Se a fonte corrigir a despesa ou um limite mudar e o alerta deixar de
disparar, ele fica **inativo**: sai do site, mas mantém o código.

## Publicação

O texto é um modelo único para todos os parlamentares:

```
[Câmara] Dep. {nome} ({partido}-{uf}) — R$ {valor} em {categoria}, {data},
fornecedor {fornecedor}. Regra: {regra}. Atípico ≠ irregular. Cód. {código}
```

- **X:** não leva link. A tarifa da API é mais alta para posts com link, então o texto
  termina com "Busque o código no site".
- **Bluesky:** leva link e card.
- **Mastodon:** leva link e o aviso completo.

Categoria e fornecedor longos são encurtados com "…", pela mesma regra para todos, até o
texto caber no limite da rede.

Não há repetição: cada alerta sai no máximo uma vez por rede. Cada rede tem um limite
diário, a fila segue a ordem de pontuação e todo envio fica registrado na tabela
`publicacoes`.
