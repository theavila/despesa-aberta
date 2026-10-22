"""Fábrica de despesas sintéticas para os testes de regras."""

from datetime import date, datetime
from itertools import count
from typing import Any

import polars as pl

from pipeline.normalizacao.esquema import COLUNAS

_ids = count(1)

ESQUEMA = {
    "id": pl.String,
    "casa": pl.String,
    "parlamentar_id": pl.String,
    "parlamentar_nome": pl.String,
    "partido": pl.String,
    "uf": pl.String,
    "data": pl.Date,
    "competencia": pl.String,
    "categoria": pl.String,
    "fornecedor_nome": pl.String,
    "fornecedor_cnpj_cpf": pl.String,
    "valor": pl.Float64,
    "url_documento": pl.String,
    "fonte": pl.String,
    "coletado_em": pl.Datetime("us"),
}
assert list(ESQUEMA) == COLUNAS


def despesa(**campos: Any) -> dict[str, Any]:
    base = {
        "id": f"d{next(_ids):05d}",
        "casa": "camara",
        "parlamentar_id": "1",
        "parlamentar_nome": "Parlamentar Exemplo",
        "partido": "PARTIDO",
        "uf": "DF",
        "data": date(2026, 3, 10),  # terça-feira
        "competencia": None,
        "categoria": "Combustíveis e lubrificantes",
        "fornecedor_nome": "FORNECEDOR LTDA",
        "fornecedor_cnpj_cpf": "11222333000181",
        "valor": 100.0,
        "url_documento": "https://exemplo.test/doc.pdf",
        "fonte": "https://exemplo.test/fonte.csv",
        "coletado_em": datetime(2026, 10, 1),
    }
    base.update(campos)
    if base["competencia"] is None:
        d = base["data"] or date(2026, 3, 1)
        base["competencia"] = f"{d.year}-{d.month:02d}"
    return base


def despesas(*linhas: dict[str, Any]) -> pl.DataFrame:
    return pl.DataFrame(list(linhas), schema=ESQUEMA)
