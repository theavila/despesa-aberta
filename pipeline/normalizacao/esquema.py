"""Esquema único de despesa, comum à Câmara e ao Senado."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Despesa(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Hash estável da linha na fonte oficial")
    casa: Literal["camara", "senado"]
    parlamentar_id: str
    parlamentar_nome: str
    partido: str | None
    uf: str | None
    data: date | None = Field(description="Data de emissão do documento fiscal")
    competencia: str = Field(pattern=r"^\d{4}-\d{2}$", description="Ano-mês de referência")
    categoria: str
    fornecedor_nome: str
    fornecedor_cnpj_cpf: str | None = Field(description="Somente dígitos (14 = CNPJ, 11 = CPF)")
    valor: float
    url_documento: str
    fonte: str
    coletado_em: datetime


COLUNAS = list(Despesa.model_fields)

DDL = """
CREATE OR REPLACE TABLE despesas (
    id VARCHAR PRIMARY KEY,
    casa VARCHAR NOT NULL,
    parlamentar_id VARCHAR NOT NULL,
    parlamentar_nome VARCHAR NOT NULL,
    partido VARCHAR,
    uf VARCHAR,
    data DATE,
    competencia VARCHAR NOT NULL,
    categoria VARCHAR NOT NULL,
    fornecedor_nome VARCHAR NOT NULL,
    fornecedor_cnpj_cpf VARCHAR,
    valor DOUBLE NOT NULL,
    url_documento VARCHAR NOT NULL,
    fonte VARCHAR NOT NULL,
    coletado_em TIMESTAMP NOT NULL
)
"""
