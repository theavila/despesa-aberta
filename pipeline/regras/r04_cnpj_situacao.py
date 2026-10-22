from typing import Any

import polars as pl

from pipeline import formatacao as fmt
from pipeline.regras.base import Contexto, Regra, resultado


def _detalhe(s: dict[str, Any]) -> str:
    if s["aberto_depois"]:
        return (
            f"Segundo a Receita Federal, o CNPJ do fornecedor começou a funcionar em "
            f"{fmt.data_curta(s['data_inicio'])}, depois da data da despesa "
            f"({fmt.data_curta(s['data'])})."
        )
    return (
        f"Segundo a Receita Federal, o CNPJ do fornecedor está com situação "
        f"'{s['situacao']}' desde {fmt.data_curta(s['data_situacao'])}, antes da data da "
        f"despesa ({fmt.data_curta(s['data'])})."
    )


def aplicar(despesas: pl.DataFrame, params: dict[str, Any], contexto: Contexto) -> pl.DataFrame:
    df = (
        despesas.filter(
            pl.col("data").is_not_null() & (pl.col("fornecedor_cnpj_cpf").str.len_chars() == 14)
        )
        .join(contexto.cnpjs, left_on="fornecedor_cnpj_cpf", right_on="cnpj", how="inner")
        .with_columns(
            (pl.col("data_inicio") > pl.col("data")).fill_null(False).alias("aberto_depois"),
            (
                pl.col("situacao").is_not_null()
                & (pl.col("situacao").str.to_uppercase() != "ATIVA")
                & (pl.col("data_situacao") <= pl.col("data"))
            )
            .fill_null(False)
            .alias("inativo"),
        )
        .filter(pl.col("aberto_depois") | pl.col("inativo"))
    )
    return resultado(
        df.select(
            pl.col("id").alias("despesa_id"),
            pl.lit(1.0).alias("intensidade"),
            pl.struct("aberto_depois", "data_inicio", "data", "situacao", "data_situacao")
            .map_elements(_detalhe, pl.String)
            .alias("detalhe"),
        )
    )


REGRA = Regra(
    id="R04_cnpj_situacao",
    nome="Fornecedor com CNPJ irregular na data",
    descricao=(
        "Consulta o cadastro do CNPJ do fornecedor na Receita Federal (via BrasilAPI). Marca a "
        "despesa se, na data dela, a empresa ainda não tinha sido aberta ou já estava com "
        "situação diferente de 'ativa' (baixada, inapta, suspensa ou nula). Empresas que "
        "fecharam depois da despesa não são marcadas."
    ),
    aplicar=aplicar,
    modulo=__name__,
)
