"""Consulta de CNPJs na BrasilAPI, com cache no DuckDB e limite de taxa."""

import logging
import time
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import duckdb
import httpx
import polars as pl

from pipeline import db
from pipeline.http import ErroDeColeta, obter

log = logging.getLogger(__name__)


def _data(texto: str | None) -> date | None:
    try:
        return date.fromisoformat(texto) if texto else None
    except ValueError:
        return None


def interpretar(corpo: dict[str, Any]) -> dict[str, Any]:
    """Extrai da resposta da BrasilAPI os campos usados pela regra R04."""
    return {
        "situacao": corpo.get("descricao_situacao_cadastral") or None,
        "data_situacao": _data(corpo.get("data_situacao_cadastral")),
        "data_inicio": _data(corpo.get("data_inicio_atividade")),
        "razao_social": corpo.get("razao_social") or None,
    }


def pendentes(
    con: duckdb.DuckDBPyConnection, validade_dias: int, limite: int, hoje: date
) -> list[str]:
    """CNPJs de fornecedores sem consulta válida no cache, do maior para o menor valor pago."""
    vencimento = hoje - timedelta(days=validade_dias)
    linhas = con.execute(
        """
        SELECT d.fornecedor_cnpj_cpf
        FROM despesas d
        LEFT JOIN cnpj_cache c ON c.cnpj = d.fornecedor_cnpj_cpf
        WHERE length(d.fornecedor_cnpj_cpf) = 14
          AND (c.cnpj IS NULL OR c.consultado_em::DATE < ?)
        GROUP BY d.fornecedor_cnpj_cpf
        ORDER BY sum(d.valor) DESC, d.fornecedor_cnpj_cpf
        LIMIT ?
        """,
        [vencimento, limite],
    ).fetchall()
    return [cnpj for (cnpj,) in linhas]


def atualizar_cache(
    con: duckdb.DuckDBPyConnection,
    cliente: httpx.Client,
    config_cnpj: dict[str, Any],
    *,
    hoje: date | None = None,
    dormir: Callable[[float], None] = time.sleep,
    **kw_retry: Any,
) -> int:
    """Consulta os CNPJs pendentes respeitando o intervalo mínimo entre requisições.

    CNPJs não encontrados ficam no cache com `erro`, para não serem consultados de novo
    antes do fim da validade. Devolve quantos CNPJs foram consultados.
    """
    cnpjs = pendentes(
        con, config_cnpj["validade_dias"], config_cnpj["max_consultas_por_execucao"],
        hoje or date.today(),
    )  # fmt: skip
    for i, cnpj in enumerate(cnpjs):
        if i:
            dormir(config_cnpj["intervalo_segundos"])
        registro: dict[str, Any] = {
            "situacao": None, "data_situacao": None, "data_inicio": None, "razao_social": None,
        }  # fmt: skip
        erro = None
        try:
            resposta = obter(
                cliente, config_cnpj["url"].format(cnpj=cnpj), dormir=dormir, **kw_retry
            )
            registro = interpretar(resposta.json())
        except httpx.HTTPStatusError as e:
            erro = f"HTTP {e.response.status_code}"
        except ErroDeColeta as e:
            log.warning("Consulta de CNPJ interrompida: %s", e)
            return i
        con.execute(
            "INSERT OR REPLACE INTO cnpj_cache VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                cnpj, registro["situacao"], registro["data_situacao"], registro["data_inicio"],
                registro["razao_social"], erro, db.agora(),
            ],
        )  # fmt: skip
    return len(cnpjs)


def carregar(con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    return db.consultar(
        con,
        "SELECT cnpj, situacao, data_situacao, data_inicio FROM cnpj_cache WHERE erro IS NULL",
    )
