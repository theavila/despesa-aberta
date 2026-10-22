import json

import polars as pl

from pipeline import db
from pipeline.coletores import camara, senado
from pipeline.coletores.base import adicionar_hash, normalizar_nome
from tests.conftest import cliente_falso

URL_CAMARA = "https://camara.test/cotas/Ano-{ano}.csv.zip"
URL_DEPUTADOS = "https://camara.test/api/v2/deputados"
URL_SENADO = "https://senado.test/despesa_ceaps_{ano}.csv"
URL_ATUAL = "https://senado.test/lista/atual"
URL_LEG = "https://senado.test/lista/legislatura/{legislatura}"


def test_normalizar_nome():
    assert normalizar_nome("  Eduardo   Girão ") == "EDUARDO GIRAO"
    assert normalizar_nome("DRA. EUDÓCIA") == "DRA. EUDOCIA"


def test_hash_estavel_e_distingue_linhas_identicas():
    df = pl.DataFrame({"a": ["1", "1", "2"], "b": ["x", "x", "y"]})
    h1 = adicionar_hash(df, "camara")["hash"].to_list()
    h2 = adicionar_hash(df, "camara")["hash"].to_list()
    assert h1 == h2
    assert len(set(h1)) == 3
    assert adicionar_hash(df, "senado")["hash"][0] != h1[0]


def test_ler_csv_camara(fixtures):
    df = camara.ler_csv((fixtures / "camara_Ano-2026.csv.zip").read_bytes())
    assert df.height == 20
    assert df.columns[0] == "txNomeParlamentar"  # BOM removido
    assert "FORNECIMENTO DE ALIMENTAÇÃO DO PARLAMENTAR" in df["txtDescricao"].to_list()
    assert df.schema["vlrLiquido"] == pl.String


def test_ler_csv_senado_pula_metadado_e_decodifica_latin1(fixtures):
    df = senado.ler_csv((fixtures / "senado_despesa_ceaps_2026.csv").read_bytes())
    assert df.height == 20
    assert df.columns[:3] == ["ANO", "MES", "SENADOR"]
    assert "EDUARDO GIRÃO" in df["SENADOR"].to_list()
    assert any("," in v for v in df["VALOR_REEMBOLSADO"].to_list())  # vírgula decimal mantida


def test_legislaturas_do_ano():
    assert senado.legislaturas_do_ano(2026) == [57]
    assert senado.legislaturas_do_ano(2027) == [57, 58]


def test_buscar_deputados_segue_paginacao():
    pag1 = {
        "dados": [{"id": 1, "nome": "Fulana de Tal", "siglaPartido": "AAA", "siglaUf": "SP"}],
        "links": [{"rel": "next", "href": "https://camara.test/pag2"}],
    }
    pag2 = {"dados": [{"id": 2, "nome": "Beltrano", "siglaPartido": "BBB", "siglaUf": "RJ"}]}
    cliente = cliente_falso(
        {
            f"{URL_DEPUTADOS}?idLegislatura=57&itens=100&ordem=ASC": json.dumps(pag1).encode(),
            "https://camara.test/pag2": json.dumps(pag2).encode(),
        }
    )
    df = camara.buscar_deputados(cliente, URL_DEPUTADOS, [57], dormir=lambda s: None)
    assert df["id"].to_list() == ["1", "2"]
    assert df["nome_normalizado"].to_list() == ["FULANA DE TAL", "BELTRANO"]


def _cliente_senado(fixtures):
    return cliente_falso(
        {
            URL_SENADO.format(ano=2026): (fixtures / "senado_despesa_ceaps_2026.csv").read_bytes(),
            URL_ATUAL: (fixtures / "senado_lista_atual.json").read_bytes(),
            URL_LEG.format(legislatura=57): (
                fixtures / "senado_lista_legislatura_57.json"
            ).read_bytes(),
        }
    )


def test_vincula_senadores_pelo_nome_normalizado(fixtures):
    cliente = _cliente_senado(fixtures)
    parlamentares = senado.buscar_senadores(cliente, URL_ATUAL, URL_LEG, 2026)
    linhas = senado.coletar(cliente, URL_SENADO, 2026)
    vinculo = senado.vincular(linhas["SENADOR"].unique().to_list(), parlamentares)
    assert all(vinculo.values()), vinculo
    # Eduardo Girão não está na lista atual da fixture: vem da lista da legislatura.
    girao = parlamentares.filter(pl.col("nome_normalizado") == "EDUARDO GIRAO")
    assert girao["uf"].item() == "CE"
    assert set(parlamentares["uf"].to_list()) <= {"AC", "BA", "DF", "CE"}


def test_vincula_pelo_nome_completo_quando_unico():
    parlamentares = pl.DataFrame(
        {
            "id": ["1", "2", "3"],
            "nome_normalizado": ["WEVERTON", "MARIA SILVA", "MARIA SOUZA"],
            "nome_completo": ["Weverton Rocha Marques de Sousa", "Maria Silva", "Maria Souza"],
        }
    )
    vinculo = senado.vincular(["WEVERTON ROCHA", "MARIA", "JOÃO NINGUÉM"], parlamentares)
    assert vinculo == {"WEVERTON ROCHA": "1", "MARIA": None, "JOÃO NINGUÉM": None}


def test_coleta_e_idempotente(fixtures):
    cliente = cliente_falso(
        {URL_CAMARA.format(ano=2026): (fixtures / "camara_Ano-2026.csv.zip").read_bytes()}
    )
    con = db.conectar(":memory:")
    linhas = camara.coletar(cliente, URL_CAMARA, 2026)
    assert db.inserir_brutos(con, linhas, "camara", 2026) == 20
    assert db.inserir_brutos(con, camara.coletar(cliente, URL_CAMARA, 2026), "camara", 2026) == 0
    dados = json.loads(db.escalar(con, "SELECT dados FROM bruto LIMIT 1"))
    assert "ideCadastro" in dados


def test_gravar_parlamentares_atualiza(fixtures):
    con = db.conectar(":memory:")
    deputados = camara.parlamentares_da_api(
        json.loads((fixtures / "camara_deputados.json").read_text(encoding="utf-8"))["dados"]
    )
    db.gravar_parlamentares(con, deputados)
    db.gravar_parlamentares(con, deputados)
    total = db.escalar(con, "SELECT count(*) FROM parlamentares")
    assert total == deputados.height > 0
