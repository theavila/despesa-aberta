"""Coletor da Cota para o Exercício da Atividade Parlamentar (CEAP) da Câmara."""

import io
import zipfile
from typing import Any

import httpx
import polars as pl

from pipeline.coletores.base import adicionar_hash, normalizar_nome
from pipeline.http import obter


def ler_csv(conteudo_zip: bytes) -> pl.DataFrame:
    """Lê o `Ano-{ano}.csv.zip`: CSV separado por `;`, UTF-8 (com BOM). Tudo como texto."""
    with zipfile.ZipFile(io.BytesIO(conteudo_zip)) as z:
        nome = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        texto = z.read(nome).decode("utf-8-sig")
    return pl.read_csv(
        io.StringIO(texto), separator=";", infer_schema=False, empty_string_is_null=False
    )


def parlamentares_da_api(dados: list[dict[str, Any]]) -> pl.DataFrame:
    """Converte a lista `dados` da API v2 de deputados na tabela de parlamentares."""
    linhas = [
        {
            "casa": "camara",
            "id": str(d["id"]),
            "nome": d["nome"],
            "nome_normalizado": normalizar_nome(d["nome"]),
            "nome_completo": None,
            "partido": d.get("siglaPartido") or None,
            "uf": d.get("siglaUf") or None,
            "url_foto": d.get("urlFoto") or None,
        }
        for d in dados
    ]
    return pl.DataFrame(linhas).unique(subset="id", keep="last", maintain_order=True)


def buscar_deputados(
    cliente: httpx.Client, url: str, legislaturas: list[int], **kw_retry: Any
) -> pl.DataFrame:
    """Busca os deputados das legislaturas indicadas, seguindo a paginação da API."""
    dados: list[dict[str, Any]] = []
    for legislatura in legislaturas:
        proxima: str | None = f"{url}?idLegislatura={legislatura}&itens=100&ordem=ASC"
        while proxima:
            corpo = obter(
                cliente, proxima, headers={"Accept": "application/json"}, **kw_retry
            ).json()
            dados.extend(corpo["dados"])
            proxima = next(
                (lk["href"] for lk in corpo.get("links", []) if lk["rel"] == "next"), None
            )
    return parlamentares_da_api(dados)


def coletar(cliente: httpx.Client, url: str, ano: int, **kw_retry: Any) -> pl.DataFrame:
    """Baixa o arquivo do ano e devolve as linhas brutas com a coluna `hash`."""
    resposta = obter(cliente, url.format(ano=ano), **kw_retry)
    return adicionar_hash(ler_csv(resposta.content), "camara")
