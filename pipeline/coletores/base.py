"""Utilidades comuns aos coletores."""

import hashlib
import unicodedata
from collections import Counter

import polars as pl


def normalizar_nome(nome: str) -> str:
    """Maiúsculas, sem acento e com espaços simples: 'Eduardo  Girão' -> 'EDUARDO GIRAO'."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", nome) if not unicodedata.combining(c)
    )
    return " ".join(sem_acento.upper().split())


def adicionar_hash(df: pl.DataFrame, casa: str) -> pl.DataFrame:
    """Acrescenta a coluna `hash`, identificador estável de cada linha da fonte.

    O hash cobre a casa e todos os campos da linha. Linhas idênticas dentro do mesmo
    arquivo recebem também o número da ocorrência, para que não sejam fundidas.
    """
    vistos: Counter[str] = Counter()
    hashes = []
    for linha in df.rows():
        conteudo = "\x1f".join("" if v is None else str(v) for v in linha)
        ocorrencia = vistos[conteudo]
        vistos[conteudo] += 1
        chave = f"{casa}\x1e{conteudo}\x1e{ocorrencia}"
        hashes.append(hashlib.sha256(chave.encode()).hexdigest())
    return df.with_columns(pl.Series("hash", hashes, dtype=pl.String))
