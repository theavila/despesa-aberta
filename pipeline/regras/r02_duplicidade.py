from typing import Any

import polars as pl

from pipeline import formatacao as fmt
from pipeline.regras.base import Contexto, Regra, na_lista, resultado

CHAVE = ["parlamentar_id", "fornecedor", "valor", "data"]


def aplicar(despesas: pl.DataFrame, params: dict[str, Any], contexto: Contexto) -> pl.DataFrame:
    df = despesas.filter(
        pl.col("data").is_not_null()
        & (pl.col("valor") >= params["valor_minimo"])
        & ~na_lista("categoria", params.get("categorias_excluidas", []))
    ).with_columns(
        pl.coalesce("fornecedor_cnpj_cpf", pl.col("fornecedor_nome").str.to_uppercase()).alias(
            "fornecedor"
        )
    )
    # A primeira despesa do grupo (pela ordem do id) é a referência; as demais disparam.
    df = (
        df.sort("id")
        .with_columns(
            pl.len().over(CHAVE).alias("ocorrencias"),
            pl.int_range(1, pl.len() + 1).over(CHAVE).alias("ordem"),
        )
        .filter(pl.col("ordem") > 1)
    )
    return resultado(
        df.select(
            pl.col("id").alias("despesa_id"),
            pl.lit(1.0).alias("intensidade"),
            pl.struct("ocorrencias", "valor", "data")
            .map_elements(
                lambda s: (
                    f"Há {s['ocorrencias']} despesas deste parlamentar com o mesmo fornecedor, "
                    f"o mesmo valor ({fmt.reais(s['valor'])}) e a mesma data "
                    f"({fmt.data_curta(s['data'])})."
                ),
                pl.String,
            )
            .alias("detalhe"),
        )
    )


REGRA = Regra(
    id="R02_duplicidade",
    nome="Possível duplicidade",
    descricao=(
        "Marca despesas do mesmo parlamentar com o mesmo fornecedor, o mesmo valor e a mesma "
        "data de outra despesa já registrada. A primeira delas não é marcada; as repetições "
        "sim. Valores pequenos e categorias em que a repetição é comum (como várias diárias "
        "de hotel na mesma noite) ficam de fora, conforme a configuração."
    ),
    aplicar=aplicar,
    modulo=__name__,
)
