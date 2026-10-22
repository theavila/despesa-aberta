"""Aplica as regras e mantém a tabela `alertas` com códigos estáveis (A-AAAA-NNNNN)."""

from typing import Any

import duckdb
import polars as pl

from pipeline import db
from pipeline.coletores import cnpj
from pipeline.regras import aplicar_regras
from pipeline.regras.base import Contexto

COLUNAS = [
    "codigo", "regra_id", "despesa_id", "score", "detalhe", "ativo", "criado_em", "atualizado_em",
]  # fmt: skip


def codigo(ano: str, sequencia: int) -> str:
    return f"A-{ano}-{sequencia:05d}"


def gravar_alertas(con: duckdb.DuckDBPyConnection, candidatos: pl.DataFrame) -> dict[str, int]:
    """Concilia os disparos atuais com os alertas já gravados.

    - Disparo já conhecido: mantém o código e atualiza score e detalhe.
    - Disparo novo: recebe o próximo código do ano da competência da despesa.
    - Alerta que deixou de disparar (dado corrigido na fonte, limite alterado): fica
      inativo, mas o código nunca é reutilizado.
    """
    agora = db.agora()
    existentes = db.consultar(con, f"SELECT {', '.join(COLUNAS)} FROM alertas")
    chave = ["regra_id", "despesa_id"]

    atuais = candidatos.select(*chave, pl.col("score").alias("novo_score"), "detalhe")
    mantidos = (
        existentes.join(atuais, on=chave, how="left", suffix="_novo")
        .with_columns(pl.col("novo_score").is_not_null().alias("ativo"))
        .with_columns(
            # Alertas inativos guardam o último score e detalhe conhecidos.
            pl.coalesce("novo_score", "score").cast(pl.Int32).alias("score"),
            pl.coalesce("detalhe_novo", "detalhe").alias("detalhe"),
            pl.lit(agora).alias("atualizado_em"),
        )
    )

    novos = candidatos.join(existentes.select(chave), on=chave, how="anti")
    if not novos.is_empty():
        despesas = db.consultar(con, "SELECT id, competencia, data FROM despesas")
        novos = (
            novos.join(despesas, left_on="despesa_id", right_on="id")
            .with_columns(pl.col("competencia").str.slice(0, 4).alias("ano"))
            .sort("competencia", "data", "despesa_id", "regra_id", nulls_last=True)
        )
        ultimo = {
            ano: int(seq)
            for ano, seq in con.execute(
                "SELECT split_part(codigo, '-', 2), max(split_part(codigo, '-', 3)::INTEGER) "
                "FROM alertas GROUP BY 1"
            ).fetchall()
        }
        novos = novos.with_columns(
            (pl.int_range(1, pl.len() + 1).over("ano")).alias("seq")
        ).with_columns(
            pl.struct("ano", "seq")
            .map_elements(lambda s: codigo(s["ano"], ultimo.get(s["ano"], 0) + s["seq"]), pl.String)
            .alias("codigo"),
            pl.lit(True).alias("ativo"),
            pl.lit(agora).alias("criado_em"),
            pl.lit(agora).alias("atualizado_em"),
        )
    partes = [mantidos.select(COLUNAS)]
    if not novos.is_empty():
        partes.append(novos.select(COLUNAS))
    tabela = pl.concat(partes, how="vertical_relaxed")
    con.execute("BEGIN TRANSACTION")
    con.execute("DELETE FROM alertas")
    con.register("tabela_alertas", tabela)
    con.execute(f"INSERT INTO alertas SELECT {', '.join(COLUNAS)} FROM tabela_alertas")
    con.unregister("tabela_alertas")
    con.execute("COMMIT")
    return {
        "novos": novos.height,
        "ativos": int(tabela["ativo"].sum()),
        "inativos": int((~tabela["ativo"]).sum()),
    }


def analisar(con: duckdb.DuckDBPyConnection, config_regras: dict[str, Any]) -> dict[str, int]:
    despesas = db.consultar(con, "SELECT * FROM despesas")
    contexto = Contexto(cnpjs=cnpj.carregar(con))
    candidatos = aplicar_regras(despesas, config_regras, contexto)
    return gravar_alertas(con, candidatos)
