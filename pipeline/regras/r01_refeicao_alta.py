from typing import Any

import polars as pl

from pipeline import formatacao as fmt
from pipeline.regras.base import Contexto, Regra, intensidade_por_razao, na_lista, resultado


def aplicar(despesas: pl.DataFrame, params: dict[str, Any], contexto: Contexto) -> pl.DataFrame:
    limite = params["limite"]
    df = despesas.filter(na_lista("categoria", params["categorias"]) & (pl.col("valor") > limite))
    return resultado(
        df.select(
            pl.col("id").alias("despesa_id"),
            intensidade_por_razao(pl.col("valor") / limite).alias("intensidade"),
            pl.col("valor")
            .map_elements(
                lambda v: (
                    f"Refeição de {fmt.reais(v)}; o limite configurado é {fmt.reais(limite)} "
                    f"({fmt.numero(v / limite)} vezes o limite)."
                ),
                pl.String,
            )
            .alias("detalhe"),
        )
    )


REGRA = Regra(
    id="R01_refeicao_alta",
    nome="Refeição acima do limite",
    descricao=(
        "Marca refeições do próprio parlamentar com valor acima de um limite fixo, igual "
        "para todos. Só se aplica às categorias que identificam refeição (na Câmara, "
        "'Fornecimento de alimentação do parlamentar'; o Senado publica alimentação junto "
        "com locomoção e hospedagem, por isso não há como separar)."
    ),
    aplicar=aplicar,
    modulo=__name__,
)
