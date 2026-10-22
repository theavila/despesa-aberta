"""Gera os JSONs que alimentam o site (`site/src/data/`); o site gera deles os downloads."""

import hashlib
import inspect
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import polars as pl

from pipeline import db
from pipeline import formatacao as fmt
from pipeline import respostas as resp
from pipeline.publicadores.base import AVISO
from pipeline.regras import POR_ID, REGRAS

log = logging.getLogger(__name__)


def chave_parlamentar(casa: str, parlamentar_id: str) -> str:
    """'camara', '204379' -> 'camara-204379'; ids derivados do nome viram slug."""
    base = parlamentar_id.removeprefix("nome:").lower().replace(" ", "-")
    return f"{casa}-{base}"


def chave_fornecedor(documento: str | None, nome: str) -> str:
    """CNPJ (14 dígitos) quando houver; senão um hash curto (não expõe CPF na URL)."""
    if documento and len(documento) == 14:
        return documento
    return "f" + hashlib.sha1(f"{documento}|{nome.upper()}".encode()).hexdigest()[:12]


def _escrever(caminho: Path, dados: Any) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(dados, ensure_ascii=False, indent=1, default=str)
    caminho.write_text(texto + "\n", encoding="utf-8")


def _alertas(con: duckdb.DuckDBPyConnection) -> pl.DataFrame:
    return db.consultar(
        con,
        """
        SELECT a.codigo, a.regra_id, a.score, a.detalhe, a.criado_em,
               d.casa, d.parlamentar_id, d.parlamentar_nome, d.partido, d.uf, d.data,
               d.competencia, d.categoria, d.fornecedor_nome, d.fornecedor_cnpj_cpf,
               d.valor, d.url_documento, d.fonte
        FROM alertas a JOIN despesas d ON d.id = a.despesa_id
        WHERE a.ativo
        ORDER BY a.criado_em DESC, a.codigo DESC
        """,
    )


def exportar_alertas(alertas: pl.DataFrame, respostas: dict[str, list]) -> list[dict[str, Any]]:
    saida = []
    for a in alertas.iter_rows(named=True):
        saida.append(
            {
                "codigo": a["codigo"],
                "regra_id": a["regra_id"],
                "regra_nome": POR_ID[a["regra_id"]].nome,
                "score": a["score"],
                "detalhe": a["detalhe"],
                "criado_em": a["criado_em"].isoformat(),
                "casa": a["casa"],
                "parlamentar": chave_parlamentar(a["casa"], a["parlamentar_id"]),
                "parlamentar_nome": a["parlamentar_nome"],
                "partido": a["partido"],
                "uf": a["uf"],
                "data": a["data"].isoformat() if a["data"] else None,
                "competencia": a["competencia"],
                "categoria": a["categoria"],
                "fornecedor": chave_fornecedor(a["fornecedor_cnpj_cpf"], a["fornecedor_nome"]),
                "fornecedor_nome": a["fornecedor_nome"],
                "fornecedor_documento": fmt.cnpj_cpf(a["fornecedor_cnpj_cpf"]),
                "valor": a["valor"],
                "url_documento": a["url_documento"],
                "fonte": a["fonte"],
                "respostas": respostas.get(a["codigo"], []),
            }
        )
    return saida


def exportar_parlamentares(
    con: duckdb.DuckDBPyConnection, alertas: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    resumo = db.consultar(
        con,
        """
        -- Agregações determinísticas (o export é commitado todo dia): nome, partido e UF
        -- da despesa mais recente.
        SELECT d.casa, d.parlamentar_id,
               max_by(d.parlamentar_nome, d.competencia || d.id) AS nome,
               max_by(d.partido, d.competencia || d.id) AS partido,
               max_by(d.uf, d.competencia || d.id) AS uf, max(p.url_foto) AS url_foto,
               count(*) AS despesas, round(sum(d.valor), 2) AS total
        FROM despesas d
        LEFT JOIN parlamentares p ON p.casa = d.casa AND p.id = d.parlamentar_id
        GROUP BY ALL
        """,
    )
    categorias = db.consultar(
        con,
        """
        SELECT casa, parlamentar_id, categoria, round(sum(valor), 2) AS total
        FROM despesas GROUP BY ALL ORDER BY total DESC, categoria
        """,
    )
    meses = db.consultar(
        con,
        """
        SELECT casa, parlamentar_id, competencia, round(sum(valor), 2) AS total
        FROM despesas GROUP BY ALL ORDER BY competencia
        """,
    )

    def agrupar(df: pl.DataFrame, campo: str) -> dict[tuple[str, str], list[dict]]:
        grupos: dict[tuple[str, str], list[dict]] = {}
        for r in df.iter_rows(named=True):
            grupos.setdefault((r["casa"], r["parlamentar_id"]), []).append(
                {campo: r[campo], "total": r["total"]}
            )
        return grupos

    por_categoria = agrupar(categorias, "categoria")
    por_mes = agrupar(meses, "competencia")
    codigos: dict[str, list[str]] = {}
    for a in alertas:
        codigos.setdefault(a["parlamentar"], []).append(a["codigo"])

    saida = []
    for r in resumo.sort("casa", "nome").iter_rows(named=True):
        chave = chave_parlamentar(r["casa"], r["parlamentar_id"])
        k = (r["casa"], r["parlamentar_id"])
        saida.append(
            {
                "chave": chave,
                "casa": r["casa"],
                "id": r["parlamentar_id"],
                "nome": r["nome"],
                "partido": r["partido"],
                "uf": r["uf"],
                "url_foto": r["url_foto"],
                "despesas": r["despesas"],
                "total": r["total"],
                "por_categoria": por_categoria.get(k, []),
                "por_mes": por_mes.get(k, []),
                "alertas": codigos.get(chave, []),
            }
        )
    return saida


def exportar_fornecedores(
    con: duckdb.DuckDBPyConnection, alertas: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Só fornecedores que aparecem em algum alerta (os demais não têm página)."""
    chaves = {a["fornecedor"] for a in alertas}
    totais = db.consultar(
        con,
        """
        SELECT fornecedor_cnpj_cpf AS documento, min(fornecedor_nome) AS nome,
               upper(fornecedor_nome) AS nome_chave, count(*) AS despesas,
               count(DISTINCT casa || parlamentar_id) AS parlamentares,
               round(sum(valor), 2) AS total
        FROM despesas
        GROUP BY fornecedor_cnpj_cpf, upper(fornecedor_nome)
        -- A grafia mais frequente de cada CNPJ vem primeiro e dá nome à página.
        ORDER BY documento, despesas DESC, nome_chave
        """,
    )
    agregados: dict[str, dict[str, Any]] = {}
    for r in totais.iter_rows(named=True):
        chave = chave_fornecedor(r["documento"], r["nome_chave"])
        if chave not in chaves:
            continue
        atual = agregados.setdefault(
            chave,
            {
                "chave": chave,
                "nome": r["nome"],
                "documento": fmt.cnpj_cpf(r["documento"]),
                "despesas": 0,
                "parlamentares": 0,
                "total": 0.0,
                "alertas": [],
            },
        )
        # Um CNPJ pode aparecer com grafias diferentes do nome: soma tudo.
        atual["despesas"] += r["despesas"]
        atual["parlamentares"] = max(atual["parlamentares"], r["parlamentares"])
        atual["total"] = round(atual["total"] + r["total"], 2)
    for a in alertas:
        agregados[a["fornecedor"]]["alertas"].append(a["codigo"])
    return sorted(agregados.values(), key=lambda f: f["chave"])


def exportar_regras(config_regras: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": r.id,
            "nome": r.nome,
            "descricao": r.descricao,
            "parametros": config_regras.get(r.id, {}),
            "arquivo": f"pipeline/regras/{r.modulo.rsplit('.', 1)[-1]}.py",
            "codigo_fonte": inspect.getsource(inspect.getmodule(r.aplicar)),
        }
        for r in REGRAS
    ]


def exportar(
    con: duckdb.DuckDBPyConnection,
    config: dict[str, Any],
    destino: Path,
    pasta_respostas: Path,
    agora: datetime | None = None,
) -> dict[str, int]:
    agora = (agora or datetime.now(UTC)).astimezone(ZoneInfo(config["publicacao"]["fuso"]))
    respostas: dict[str, list] = {}
    for r in resp.carregar(pasta_respostas):
        respostas.setdefault(r.alerta, []).append(resp.como_dict(r))

    alertas = exportar_alertas(_alertas(con), respostas)
    parlamentares = exportar_parlamentares(con, alertas)
    fornecedores = exportar_fornecedores(con, alertas)
    geral = db.consultar(
        con,
        "SELECT count(*) AS despesas, round(sum(valor), 2) AS valor, min(competencia) AS inicio, "
        "max(competencia) AS fim FROM despesas",
    ).row(0, named=True)
    hoje = agora.date().isoformat()
    meta = {
        "site": config["site"],
        "atualizado_em": agora.isoformat(timespec="seconds"),
        "aviso": AVISO,
        "despesas": geral["despesas"],
        "valor_total": geral["valor"] or 0,
        "periodo": {"inicio": geral["inicio"], "fim": geral["fim"]},
        "alertas_ativos": len(alertas),
        "alertas_hoje": sum(
            1
            for a in alertas
            if datetime.fromisoformat(a["criado_em"])
            .replace(tzinfo=UTC)
            .astimezone(agora.tzinfo)
            .date()
            .isoformat()
            == hoje
        ),
        "por_regra": {r.id: sum(1 for a in alertas if a["regra_id"] == r.id) for r in REGRAS},
        "parlamentares": len(parlamentares),
        "respostas": sum(len(v) for v in respostas.values()),
    }
    _escrever(destino / "meta.json", meta)
    _escrever(destino / "alertas.json", alertas)
    _escrever(destino / "parlamentares.json", parlamentares)
    _escrever(destino / "fornecedores.json", fornecedores)
    _escrever(destino / "regras.json", exportar_regras(config["regras"]))
    _escrever(destino / "respostas.json", [r for v in respostas.values() for r in v])
    return {
        "alertas": len(alertas),
        "parlamentares": len(parlamentares),
        "fornecedores": len(fornecedores),
    }
