"""Converte as linhas brutas de cada casa para o esquema único `Despesa`."""

import json
import logging
import re

import duckdb
import polars as pl
from pydantic import TypeAdapter

from pipeline import db
from pipeline.coletores import senado
from pipeline.coletores.base import normalizar_nome
from pipeline.normalizacao.esquema import COLUNAS, DDL, Despesa

log = logging.getLogger(__name__)

# Nomes próprios e siglas que voltam à grafia original depois de passar para minúsculas.
GRAFIAS = {"distrito federal": "Distrito Federal", " rpa": " RPA"}

URL_DEPUTADO = "https://www.camara.leg.br/deputados/{}"
URL_SENADOR = "https://www6g.senado.leg.br/transparencia/sen/{}/?ano={}"


def limpar_categoria(texto: str) -> str:
    """Espaços simples, sem ponto final e, se vier toda em caixa alta, só a inicial maiúscula.

    'COMBUSTÍVEIS E LUBRIFICANTES.' -> 'Combustíveis e lubrificantes'
    """
    texto = re.sub(r"\s*,\s*", ", ", " ".join(texto.split())).rstrip(" .")
    if not texto:
        return "Não informada"
    if texto.isupper():
        texto = texto.lower()
        for minusculo, grafia in GRAFIAS.items():
            texto = texto.replace(minusculo, grafia)
    return texto[0].upper() + texto[1:]


def _somente_digitos(coluna: str) -> pl.Expr:
    digitos = pl.col(coluna).str.replace_all(r"\D", "")
    return pl.when(digitos == "").then(None).otherwise(digitos)


def _texto_ou_nulo(coluna: str) -> pl.Expr:
    texto = pl.col(coluna).str.strip_chars()
    return pl.when(texto == "").then(None).otherwise(texto)


def _competencia(ano: str, mes: str) -> pl.Expr:
    return pl.col(ano) + "-" + pl.col(mes).str.zfill(2)


def _fonte(url: str) -> pl.Expr:
    return pl.format(url.replace("{ano}", "{}"), pl.col("ano"))


def _expandir(brutos: pl.DataFrame) -> pl.DataFrame:
    """Transforma a coluna JSON `dados` em colunas de texto."""
    dados = pl.DataFrame([json.loads(d) for d in brutos["dados"]], infer_schema_length=None)
    return pl.concat(
        [brutos.select("hash", "coletado_em", "ano"), dados.cast(pl.String).fill_null("")],
        how="horizontal",
    )


def normalizar_camara(brutos: pl.DataFrame, fonte: str) -> pl.DataFrame:
    """Linhas sem `ideCadastro` (lideranças e órgãos da Casa) não são de um parlamentar e
    ficam de fora."""
    if brutos.is_empty():
        return pl.DataFrame()
    df = _expandir(brutos).filter(pl.col("ideCadastro").str.strip_chars() != "")
    return df.select(
        pl.col("hash").alias("id"),
        pl.lit("camara").alias("casa"),
        pl.col("ideCadastro").alias("parlamentar_id"),
        pl.col("txNomeParlamentar").str.strip_chars().alias("parlamentar_nome"),
        _texto_ou_nulo("sgPartido").alias("partido"),
        _texto_ou_nulo("sgUF").alias("uf"),
        pl.col("datEmissao").str.slice(0, 10).str.to_date("%Y-%m-%d", strict=False).alias("data"),
        _competencia("numAno", "numMes").alias("competencia"),
        pl.col("txtDescricao").map_elements(limpar_categoria, pl.String).alias("categoria"),
        pl.col("txtFornecedor").str.strip_chars().alias("fornecedor_nome"),
        _somente_digitos("txtCNPJCPF").alias("fornecedor_cnpj_cpf"),
        pl.col("vlrLiquido").cast(pl.Float64).round(2).alias("valor"),
        pl.coalesce(
            _texto_ou_nulo("urlDocumento"), pl.format(URL_DEPUTADO, pl.col("ideCadastro"))
        ).alias("url_documento"),
        _fonte(fonte).alias("fonte"),
        pl.col("coletado_em"),
    )


def normalizar_senado(
    brutos: pl.DataFrame, parlamentares: pl.DataFrame, fonte: str
) -> pl.DataFrame:
    """Senadores sem vínculo oficial recebem um id derivado do nome (`nome:<NOME>`)."""
    if brutos.is_empty():
        return pl.DataFrame()
    df = _expandir(brutos)
    vinculo = senado.vincular(df["SENADOR"].unique().to_list(), parlamentares)
    sem_vinculo = sorted(nome for nome, id_ in vinculo.items() if id_ is None)
    if sem_vinculo:
        log.warning("Senadores sem vínculo oficial: %s", ", ".join(sem_vinculo))
    ids = pl.DataFrame(
        {
            "SENADOR": list(vinculo),
            "parlamentar_id": [id_ or f"nome:{normalizar_nome(n)}" for n, id_ in vinculo.items()],
            "vinculado": [id_ is not None for id_ in vinculo.values()],
        }
    )
    cadastro = parlamentares.select(
        pl.col("id").alias("parlamentar_id"), pl.col("nome").alias("nome_oficial"), "partido", "uf"
    )
    df = df.join(ids, on="SENADOR", how="left").join(cadastro, on="parlamentar_id", how="left")
    return df.select(
        pl.col("hash").alias("id"),
        pl.lit("senado").alias("casa"),
        pl.col("parlamentar_id"),
        pl.coalesce("nome_oficial", pl.col("SENADOR").str.to_titlecase()).alias("parlamentar_nome"),
        pl.col("partido"),
        pl.col("uf"),
        pl.col("DATA").str.to_date("%d/%m/%Y", strict=False).alias("data"),
        _competencia("ANO", "MES").alias("competencia"),
        pl.col("TIPO_DESPESA").map_elements(limpar_categoria, pl.String).alias("categoria"),
        pl.col("FORNECEDOR").str.strip_chars().alias("fornecedor_nome"),
        _somente_digitos("CNPJ_CPF").alias("fornecedor_cnpj_cpf"),
        pl.col("VALOR_REEMBOLSADO")
        .str.replace_all(".", "", literal=True)
        .str.replace(",", ".", literal=True)
        .cast(pl.Float64)
        .round(2)
        .alias("valor"),
        pl.when(pl.col("vinculado"))
        .then(pl.format(URL_SENADOR, pl.col("parlamentar_id"), pl.col("ANO")))
        .otherwise(_fonte(fonte))
        .alias("url_documento"),
        _fonte(fonte).alias("fonte"),
        pl.col("coletado_em"),
    )


def validar(df: pl.DataFrame) -> list[Despesa]:
    """Valida cada linha contra o esquema `Despesa` (falha se algo vier fora do padrão)."""
    return TypeAdapter(list[Despesa]).validate_python(df.select(COLUNAS).to_dicts())


def normalizar(con: duckdb.DuckDBPyConnection, urls: dict[str, str]) -> int:
    """Reconstrói a tabela `despesas` a partir de `bruto`. Devolve o total de despesas."""

    def brutos(casa: str) -> pl.DataFrame:
        return db.consultar(
            con,
            "SELECT hash, ano, dados::VARCHAR AS dados, coletado_em FROM bruto WHERE casa = ?",
            [casa],
        )

    senadores = db.consultar(
        con,
        "SELECT id, nome, nome_normalizado, nome_completo, partido, uf "
        "FROM parlamentares WHERE casa = 'senado'",
    )
    partes = [
        normalizar_camara(brutos("camara"), urls["camara_cotas"]),
        normalizar_senado(brutos("senado"), senadores, urls["senado_ceaps"]),
    ]
    despesas = pl.concat([p.select(COLUNAS) for p in partes if not p.is_empty()])
    validar(despesas)
    con.execute(DDL)
    con.register("novas_despesas", despesas)
    con.execute("INSERT INTO despesas SELECT * FROM novas_despesas")
    con.unregister("novas_despesas")
    return despesas.height
