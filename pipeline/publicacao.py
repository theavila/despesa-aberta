"""Fila de publicação: ordem por score, limite diário por rede, sem repetir alertas."""

import logging
import os
from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import duckdb

from pipeline import db
from pipeline.publicadores.base import AlertaPublicavel, Publicador, Resultado
from pipeline.publicadores.bluesky import PublicadorBluesky
from pipeline.publicadores.mastodon import PublicadorMastodon
from pipeline.publicadores.x import PublicadorX
from pipeline.regras import POR_ID

log = logging.getLogger(__name__)


def publicacao_ativada() -> bool:
    """Só publica de verdade com PUBLICAR=1; em qualquer outro caso, dry-run."""
    return os.environ.get("PUBLICAR") == "1"


def redes_ativas() -> set[str] | None:
    """Redes listadas em REDES_ATIVAS (ex.: "bluesky,x"); vazio ou ausente = todas."""
    redes = {r.strip().lower() for r in os.environ.get("REDES_ATIVAS", "").split(",") if r.strip()}
    return redes or None


def criar_publicadores(nome_site: str) -> list[Publicador]:
    return [PublicadorX(nome_site), PublicadorBluesky(nome_site), PublicadorMastodon(nome_site)]


def url_alerta(url_site: str, codigo: str) -> str:
    return f"{url_site.rstrip('/')}/alerta/{codigo}/"


def publicados_hoje(
    con: duckdb.DuckDBPyConnection, rede: str, fuso: str, agora: datetime | None = None
) -> int:
    """Publicações bem-sucedidas na rede desde a meia-noite local (horários gravados em UTC)."""
    agora = agora or datetime.now(UTC)
    local = agora.astimezone(ZoneInfo(fuso))
    inicio = datetime.combine(local.date(), time(), ZoneInfo(fuso)).astimezone(UTC)
    return db.escalar(
        con,
        "SELECT count(*) FROM publicacoes WHERE rede = ? AND sucesso AND publicado_em >= ?",
        [rede, inicio.replace(tzinfo=None)],
    )


def fila(
    con: duckdb.DuckDBPyConnection, rede: str, limite: int, url_site: str
) -> list[AlertaPublicavel]:
    """Alertas ativos ainda não publicados na rede, do maior para o menor score."""
    if limite <= 0:
        return []
    linhas = db.consultar(
        con,
        """
        SELECT a.codigo, d.casa, d.parlamentar_nome, d.partido, d.uf, d.valor, d.categoria,
               d.data, d.fornecedor_nome, a.regra_id, a.score
        FROM alertas a
        JOIN despesas d ON d.id = a.despesa_id
        WHERE a.ativo
          AND a.codigo NOT IN (SELECT codigo FROM publicacoes WHERE rede = ? AND sucesso)
        ORDER BY a.score DESC, d.valor DESC, a.codigo
        LIMIT ?
        """,
        [rede, limite],
    )
    return [
        AlertaPublicavel(
            codigo=r["codigo"],
            casa=r["casa"],
            parlamentar_nome=r["parlamentar_nome"],
            partido=r["partido"],
            uf=r["uf"],
            valor=r["valor"],
            categoria=r["categoria"],
            data=r["data"],
            fornecedor_nome=r["fornecedor_nome"],
            regra_nome=POR_ID[r["regra_id"]].nome,
            score=r["score"],
            url=url_alerta(url_site, r["codigo"]),
        )
        for r in linhas.iter_rows(named=True)
    ]


def registrar(con: duckdb.DuckDBPyConnection, resultado: Resultado) -> None:
    con.execute(
        "INSERT INTO publicacoes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            resultado.rede, resultado.codigo, db.agora(), resultado.sucesso,
            resultado.id_externo, resultado.url, resultado.texto, resultado.erro,
        ],
    )  # fmt: skip


def publicar(
    con: duckdb.DuckDBPyConnection,
    publicadores: list[Publicador],
    config: dict[str, Any],
    *,
    dry_run: bool,
    limite: int | None = None,
    agora: datetime | None = None,
) -> list[Resultado]:
    """Publica até `por_execucao` alertas por rede, respeitando o limite diário.

    Em dry-run nada é enviado nem gravado; os textos são só devolvidos.
    Redes sem credenciais são puladas (com aviso) quando a publicação é real.
    """
    conf = config["publicacao"]
    resultados = []
    for publicador in publicadores:
        if not dry_run and not publicador.configurado():
            log.warning("%s: credenciais ausentes; rede ignorada", publicador.rede)
            continue
        restante = conf["limite_diario"].get(publicador.rede, 0) - publicados_hoje(
            con, publicador.rede, conf["fuso"], agora
        )
        quantidade = min(limite if limite is not None else conf["por_execucao"], restante)
        for alerta in fila(con, publicador.rede, quantidade, config["site"]["url"]):
            resultado = publicador.publicar(alerta, dry_run=dry_run)
            if not dry_run:
                registrar(con, resultado)
            resultados.append(resultado)
    return resultados
