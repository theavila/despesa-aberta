from datetime import date
from typing import Any

import polars as pl

from pipeline import formatacao as fmt
from pipeline.regras.base import Contexto, Regra, na_lista, resultado
from pipeline.regras.feriados import feriado


def motivo(d: date) -> str | None:
    """'sábado', 'domingo', 'feriado nacional (Tiradentes)' ou None em dia útil."""
    if nome := feriado(d):
        return f"feriado nacional ({nome})"
    if d.weekday() >= 5:
        return fmt.DIAS_DA_SEMANA[d.weekday()]
    return None


def aplicar(despesas: pl.DataFrame, params: dict[str, Any], contexto: Contexto) -> pl.DataFrame:
    df = despesas.filter(
        pl.col("data").is_not_null()
        & (pl.col("valor") >= params["valor_minimo"])
        & na_lista("categoria", params["categorias"])
    ).with_columns(pl.col("data").map_elements(motivo, pl.String).alias("motivo"))
    df = df.filter(pl.col("motivo").is_not_null())
    return resultado(
        df.select(
            pl.col("id").alias("despesa_id"),
            pl.lit(1.0).alias("intensidade"),
            pl.struct("data", "motivo")
            .map_elements(
                lambda s: (
                    f"Documento de despesa de expediente emitido em "
                    f"{fmt.data_curta(s['data'])}, {s['motivo']}."
                ),
                pl.String,
            )
            .alias("detalhe"),
        )
    )


REGRA = Regra(
    id="R05_fim_de_semana",
    nome="Despesa de expediente em fim de semana ou feriado",
    descricao=(
        "Marca despesas de categorias típicas de expediente de escritório (manutenção de "
        "escritório, aluguel, material de consumo, consultorias, divulgação, publicações e "
        "serviços postais) cujo documento foi emitido num sábado, domingo ou feriado "
        "nacional."
    ),
    aplicar=aplicar,
    modulo=__name__,
)
