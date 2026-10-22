"""Coletor da Cota para o Exercício da Atividade Parlamentar dos Senadores (CEAPS)."""

import io
from typing import Any

import httpx
import polars as pl

from pipeline.coletores.base import adicionar_hash, normalizar_nome
from pipeline.http import obter


def ler_csv(conteudo: bytes) -> pl.DataFrame:
    """Lê o CSV do CEAPS: Latin-1, `;`, e a PRIMEIRA LINHA é metadado ("ULTIMA ATUALIZACAO").

    Os valores (com vírgula decimal) ficam como texto; a conversão é da normalização.
    """
    texto = conteudo.decode("latin-1")
    _metadado, _, resto = texto.partition("\n")
    return pl.read_csv(
        io.StringIO(resto), separator=";", infer_schema=False, empty_string_is_null=False
    )


def legislaturas_do_ano(ano: int) -> list[int]:
    """Legislaturas que cobrem o ano (a troca ocorre em 1º de fevereiro dos anos 4k+3)."""
    return sorted({(ano - 1 - 1795) // 4, (ano - 1795) // 4})


def _lista(corpo: dict[str, Any]) -> list[dict[str, Any]]:
    raiz = next(iter(corpo.values()))
    parlamentares = raiz.get("Parlamentares", {}).get("Parlamentar", [])
    return parlamentares if isinstance(parlamentares, list) else [parlamentares]


def _uf(p: dict[str, Any]) -> str | None:
    ident = p["IdentificacaoParlamentar"]
    if ident.get("UfParlamentar"):
        return ident["UfParlamentar"]
    mandatos = p.get("Mandato") or p.get("Mandatos", {}).get("Mandato")
    if isinstance(mandatos, dict):
        mandatos = [mandatos]
    for mandato in mandatos or []:
        if mandato.get("UfParlamentar"):
            return mandato["UfParlamentar"]
    return None


def parlamentares_das_listas(listas: list[dict[str, Any]]) -> pl.DataFrame:
    """Une as listas oficiais (a primeira tem precedência) numa tabela de parlamentares."""
    linhas: dict[str, dict[str, Any]] = {}
    for corpo in listas:
        for p in _lista(corpo):
            ident = p["IdentificacaoParlamentar"]
            codigo = str(ident["CodigoParlamentar"])
            if codigo in linhas:
                continue
            linhas[codigo] = {
                "casa": "senado",
                "id": codigo,
                "nome": ident["NomeParlamentar"],
                "nome_normalizado": normalizar_nome(ident["NomeParlamentar"]),
                "nome_completo": ident.get("NomeCompletoParlamentar") or None,
                "partido": ident.get("SiglaPartidoParlamentar") or None,
                "uf": _uf(p),
                "url_foto": ident.get("UrlFotoParlamentar") or None,
            }
    return pl.DataFrame(list(linhas.values()))


def buscar_senadores(
    cliente: httpx.Client, url_atual: str, url_legislatura: str, ano: int, **kw_retry: Any
) -> pl.DataFrame:
    """Lista atual + listas das legislaturas do ano (para quem já deixou o mandato)."""
    urls = [url_atual] + [url_legislatura.format(legislatura=n) for n in legislaturas_do_ano(ano)]
    listas = [
        obter(cliente, u, headers={"Accept": "application/json"}, **kw_retry).json() for u in urls
    ]
    return parlamentares_das_listas(listas)


def vincular(nomes: list[str], parlamentares: pl.DataFrame) -> dict[str, str | None]:
    """Liga o nome do CSV ao código oficial do senador.

    1. Nome parlamentar normalizado idêntico.
    2. Se não houver, o único senador cujo nome completo contém todas as palavras do nome
       do CSV (ex.: "WEVERTON ROCHA" -> "Weverton Rocha Marques de Sousa").
    Sem correspondência única, o vínculo fica vazio.
    """
    por_nome = dict(zip(parlamentares["nome_normalizado"], parlamentares["id"], strict=True))
    completos = [
        (set(normalizar_nome(completo).split()), id_)
        for completo, id_ in zip(parlamentares["nome_completo"], parlamentares["id"], strict=True)
        if completo
    ]
    vinculo: dict[str, str | None] = {}
    for nome in nomes:
        normalizado = normalizar_nome(nome)
        if normalizado in por_nome:
            vinculo[nome] = por_nome[normalizado]
            continue
        palavras = set(normalizado.split())
        candidatos = {id_ for tokens, id_ in completos if palavras <= tokens}
        vinculo[nome] = candidatos.pop() if len(candidatos) == 1 else None
    return vinculo


def coletar(cliente: httpx.Client, url: str, ano: int, **kw_retry: Any) -> pl.DataFrame:
    """Baixa o arquivo do ano e devolve as linhas brutas com a coluna `hash`."""
    resposta = obter(cliente, url.format(ano=ano), **kw_retry)
    return adicionar_hash(ler_csv(resposta.content), "senado")
