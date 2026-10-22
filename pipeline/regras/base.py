"""Contrato comum das regras de atipicidade.

Cada regra é uma função pura: recebe as despesas normalizadas, os parâmetros do
`config.toml` e o contexto (dados auxiliares já carregados) e devolve um DataFrame com
as colunas de `COLUNAS_RESULTADO`, uma linha por despesa que disparou a regra.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from pipeline.coletores.base import normalizar_nome

COLUNAS_RESULTADO = {"despesa_id": pl.String, "intensidade": pl.Float64, "detalhe": pl.String}

ESQUEMA_CNPJ = {
    "cnpj": pl.String,
    "situacao": pl.String,
    "data_situacao": pl.Date,
    "data_inicio": pl.Date,
}


@dataclass(frozen=True)
class Contexto:
    """Dados externos às despesas que algumas regras consultam."""

    cnpjs: pl.DataFrame = field(default_factory=lambda: pl.DataFrame(schema=ESQUEMA_CNPJ))


Aplicar = Callable[[pl.DataFrame, dict[str, Any], Contexto], pl.DataFrame]


@dataclass(frozen=True)
class Regra:
    id: str
    nome: str
    descricao: str
    aplicar: Aplicar
    modulo: str


def resultado(df: pl.DataFrame) -> pl.DataFrame:
    """Garante colunas e tipos do resultado de uma regra."""
    if df.is_empty():
        return pl.DataFrame(schema=COLUNAS_RESULTADO)
    return df.select(pl.col(c).cast(t) for c, t in COLUNAS_RESULTADO.items())


def intensidade_por_razao(razao: pl.Expr, teto: float = 5.0) -> pl.Expr:
    """Quanto o valor excede o limite, de 0 a 1: (valor ÷ limite), limitado a `teto`, ÷ `teto`."""
    return pl.min_horizontal(razao, pl.lit(teto)) / teto


def na_lista(coluna: str, categorias: list[str]) -> pl.Expr:
    """Compara categorias sem acento e sem diferenciar maiúsculas."""
    alvos = [normalizar_nome(c) for c in categorias]
    return pl.col(coluna).map_elements(normalizar_nome, pl.String).is_in(alvos)
