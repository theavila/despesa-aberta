"""Acesso ao DuckDB: esquema e gravação idempotente."""

from datetime import UTC, datetime
from pathlib import Path

import duckdb
import polars as pl

ESQUEMA = """
CREATE TABLE IF NOT EXISTS bruto (
    hash VARCHAR PRIMARY KEY,
    casa VARCHAR NOT NULL,
    ano INTEGER NOT NULL,
    dados JSON NOT NULL,
    coletado_em TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS parlamentares (
    casa VARCHAR NOT NULL,
    id VARCHAR NOT NULL,
    nome VARCHAR NOT NULL,
    nome_normalizado VARCHAR NOT NULL,
    nome_completo VARCHAR,
    partido VARCHAR,
    uf VARCHAR,
    url_foto VARCHAR,
    atualizado_em TIMESTAMP NOT NULL,
    PRIMARY KEY (casa, id)
);
"""


def conectar(caminho: Path | str) -> duckdb.DuckDBPyConnection:
    if str(caminho) != ":memory:":
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(caminho))
    con.execute(ESQUEMA)
    return con


def escalar(con: duckdb.DuckDBPyConnection, sql: str, parametros: list | None = None):
    """Executa uma consulta e devolve o primeiro valor da primeira linha."""
    linhas = con.execute(sql, parametros or []).fetchall()
    return linhas[0][0] if linhas else None


def agora() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def inserir_brutos(
    con: duckdb.DuckDBPyConnection, linhas: pl.DataFrame, casa: str, ano: int
) -> int:
    """Grava linhas brutas ainda não vistas (pelo `hash`). Devolve quantas eram novas."""
    if linhas.is_empty():
        return 0
    campos = [c for c in linhas.columns if c != "hash"]
    novos = pl.DataFrame(
        {
            "hash": linhas["hash"],
            "casa": casa,
            "ano": ano,
            "dados": linhas.select(pl.struct(campos).struct.json_encode()).to_series(),
            "coletado_em": agora(),
        }
    )
    antes = escalar(con, "SELECT count(*) FROM bruto")
    con.register("novos", novos)
    con.execute("INSERT OR IGNORE INTO bruto SELECT hash, casa, ano, dados, coletado_em FROM novos")
    con.unregister("novos")
    return escalar(con, "SELECT count(*) FROM bruto") - antes


def gravar_parlamentares(con: duckdb.DuckDBPyConnection, parlamentares: pl.DataFrame) -> None:
    """Insere ou atualiza o cadastro de parlamentares."""
    if parlamentares.is_empty():
        return
    df = parlamentares.with_columns(pl.lit(agora()).alias("atualizado_em"))
    con.register("novos_parlamentares", df)
    con.execute(
        """
        INSERT OR REPLACE INTO parlamentares
        SELECT casa, id, nome, nome_normalizado, nome_completo, partido, uf, url_foto, atualizado_em
        FROM novos_parlamentares
        """
    )
    con.unregister("novos_parlamentares")
