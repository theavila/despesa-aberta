"""Registro das regras de atipicidade e aplicação de todas sobre as despesas."""

from typing import Any

import polars as pl

from pipeline.regras import (
    r01_refeicao_alta,
    r02_duplicidade,
    r03_outlier_categoria,
    r04_cnpj_situacao,
    r05_fim_de_semana,
)
from pipeline.regras.base import Contexto, Regra

REGRAS: list[Regra] = [
    r01_refeicao_alta.REGRA,
    r02_duplicidade.REGRA,
    r03_outlier_categoria.REGRA,
    r04_cnpj_situacao.REGRA,
    r05_fim_de_semana.REGRA,
]
POR_ID = {r.id: r for r in REGRAS}

ESQUEMA_ALERTAS = {
    "regra_id": pl.String,
    "despesa_id": pl.String,
    "intensidade": pl.Float64,
    "score": pl.Int64,
    "detalhe": pl.String,
}


def aplicar_regras(
    despesas: pl.DataFrame, config_regras: dict[str, dict[str, Any]], contexto: Contexto
) -> pl.DataFrame:
    """Aplica as regras configuradas. score = round(100 × peso × intensidade)."""
    partes = []
    for regra in REGRAS:
        params = config_regras.get(regra.id)
        if params is None:
            continue
        disparos = regra.aplicar(despesas, params, contexto)
        partes.append(
            disparos.with_columns(
                pl.lit(regra.id).alias("regra_id"),
                (pl.col("intensidade") * params["peso"] * 100)
                .round(0)
                .cast(pl.Int64)
                .alias("score"),
            )
        )
    if not partes:
        return pl.DataFrame(schema=ESQUEMA_ALERTAS)
    return pl.concat(partes).select(list(ESQUEMA_ALERTAS))
