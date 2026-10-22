import json
from datetime import date

import polars as pl
import pytest

from pipeline import db
from pipeline.coletores import camara, senado
from pipeline.normalizacao.normalizar import limpar_categoria, normalizar
from tests.conftest import cliente_falso

URLS = {
    "camara_cotas": "https://camara.test/cotas/Ano-{ano}.csv.zip",
    "senado_ceaps": "https://senado.test/despesa_ceaps_{ano}.csv",
}
URL_ATUAL = "https://senado.test/lista/atual"
URL_LEG = "https://senado.test/lista/legislatura/{legislatura}"


@pytest.fixture
def con(fixtures):
    cliente = cliente_falso(
        {
            URLS["camara_cotas"].format(ano=2026): (
                fixtures / "camara_Ano-2026.csv.zip"
            ).read_bytes(),
            URLS["senado_ceaps"].format(ano=2026): (
                fixtures / "senado_despesa_ceaps_2026.csv"
            ).read_bytes(),
            URL_ATUAL: (fixtures / "senado_lista_atual.json").read_bytes(),
            URL_LEG.format(legislatura=57): (
                fixtures / "senado_lista_legislatura_57.json"
            ).read_bytes(),
        }
    )
    con = db.conectar(":memory:")
    deputados = json.loads((fixtures / "camara_deputados.json").read_text(encoding="utf-8"))
    db.gravar_parlamentares(con, camara.parlamentares_da_api(deputados["dados"]))
    db.gravar_parlamentares(con, senado.buscar_senadores(cliente, URL_ATUAL, URL_LEG, 2026))
    db.inserir_brutos(con, camara.coletar(cliente, URLS["camara_cotas"], 2026), "camara", 2026)
    db.inserir_brutos(con, senado.coletar(cliente, URLS["senado_ceaps"], 2026), "senado", 2026)
    return con


def _despesas(con) -> pl.DataFrame:
    return db.consultar(con, "SELECT * FROM despesas")


def test_limpar_categoria():
    assert limpar_categoria("COMBUSTÍVEIS E LUBRIFICANTES.") == "Combustíveis e lubrificantes"
    assert (
        limpar_categoria("HOSPEDAGEM ,EXCETO DO PARLAMENTAR") == "Hospedagem, exceto do parlamentar"
    )
    assert limpar_categoria("Divulgação da atividade parlamentar") == (
        "Divulgação da atividade parlamentar"
    )
    assert limpar_categoria("PASSAGEM AÉREA - RPA") == "Passagem aérea - RPA"
    assert limpar_categoria("  ") == "Não informada"


def test_normaliza_as_duas_casas(con):
    # 20 linhas da Câmara menos 1 de liderança + 20 do Senado
    assert normalizar(con, URLS) == 39
    df = _despesas(con)
    assert df.group_by("casa").len().sort("casa").to_dicts() == [
        {"casa": "camara", "len": 19},
        {"casa": "senado", "len": 20},
    ]
    assert df["valor"].null_count() == 0
    assert df["url_documento"].str.starts_with("https://").all()
    assert df["competencia"].str.contains(r"^\d{4}-\d{2}$").all()


def test_campos_da_camara(con):
    normalizar(con, URLS)
    linha = _despesas(con).filter(pl.col("parlamentar_nome") == "Fausto Pinato").row(0, named=True)
    assert linha["parlamentar_id"] == "66828"
    assert (linha["partido"], linha["uf"]) == ("UNIÃO", "SP")
    assert linha["data"] == date(2026, 8, 23)
    assert linha["competencia"] == "2026-08"
    assert linha["categoria"] == "Combustíveis e lubrificantes"
    assert linha["fornecedor_cnpj_cpf"] == "08740742000165"
    assert linha["valor"] == 125.01
    assert linha["fonte"] == "https://camara.test/cotas/Ano-2026.csv.zip"


def test_camara_sem_data_e_sem_url(con):
    normalizar(con, URLS)
    linha = _despesas(con).filter(pl.col("parlamentar_id") == "62881").row(0, named=True)
    assert linha["data"] is None
    assert linha["competencia"] == "2026-01"
    assert linha["url_documento"] == "https://www.camara.leg.br/deputados/62881"


def test_campos_do_senado(con):
    normalizar(con, URLS)
    df = _despesas(con).filter(pl.col("casa") == "senado")
    assert df["parlamentar_id"].str.contains(r"^\d+$").all()  # todos vinculados
    girao = df.filter(pl.col("parlamentar_nome") == "Eduardo Girão")
    assert girao.height == 5
    assert girao["uf"].unique().to_list() == ["CE"]
    assert girao["url_documento"][0].startswith("https://www6g.senado.leg.br/transparencia/sen/")
    assert df["valor"].dtype == pl.Float64
    assert 462.18 in df["valor"].to_list()  # "462,18" no CSV


def test_senador_sem_vinculo_recebe_id_pelo_nome(con):
    con.execute("DELETE FROM parlamentares WHERE casa = 'senado' AND nome = 'Eduardo Girão'")
    normalizar(con, URLS)
    girao = _despesas(con).filter(pl.col("parlamentar_id") == "nome:EDUARDO GIRAO")
    assert girao.height == 5
    assert girao["parlamentar_nome"][0] == "Eduardo Girão"
    assert girao["url_documento"][0] == "https://senado.test/despesa_ceaps_2026.csv"


def test_normalizacao_e_reproduzivel(con):
    normalizar(con, URLS)
    primeira = _despesas(con).sort("id")
    normalizar(con, URLS)
    assert _despesas(con).sort("id").equals(primeira)
