from typing import Any

import polars as pl

from pipeline import formatacao as fmt
from pipeline.regras.base import Contexto, Regra, intensidade_por_razao, resultado

GRUPO = ["categoria", "ano"]


def aplicar(despesas: pl.DataFrame, params: dict[str, Any], contexto: Contexto) -> pl.DataFrame:
    percentil = params["percentil"]
    df = (
        despesas.filter(pl.col("valor") > 0)
        .with_columns(pl.col("competencia").str.slice(0, 4).alias("ano"))
        .with_columns(
            pl.len().over(GRUPO).alias("amostra"),
            pl.col("valor").quantile(percentil, "linear").over(GRUPO).alias("limiar"),
        )
        .filter(
            (pl.col("amostra") >= params["amostra_minima"]) & (pl.col("valor") > pl.col("limiar"))
        )
    )
    rotulo = f"percentil {fmt.numero(percentil * 100, 0)}"
    return resultado(
        df.select(
            pl.col("id").alias("despesa_id"),
            intensidade_por_razao(pl.col("valor") / pl.col("limiar")).alias("intensidade"),
            pl.struct("valor", "limiar", "ano", "amostra")
            .map_elements(
                lambda s: (
                    f"Valor de {fmt.reais(s['valor'])}, acima do {rotulo} da categoria em "
                    f"{s['ano']} ({fmt.reais(s['limiar'])}, calculado sobre "
                    f"{s['amostra']} despesas)."
                ),
                pl.String,
            )
            .alias("detalhe"),
        )
    )


REGRA = Regra(
    id="R03_outlier_categoria",
    nome="Valor muito acima do comum na categoria",
    descricao=(
        "Para cada categoria de despesa e cada ano, calcula o valor abaixo do qual estão 99% "
        "das despesas (percentil 99) de todos os parlamentares. Marca as despesas acima "
        "desse valor. Categorias com poucas despesas no ano não são avaliadas."
    ),
    aplicar=aplicar,
    modulo=__name__,
)
