import json
from datetime import UTC, date, datetime

import pytest

from pipeline import config as cfg
from pipeline import db
from pipeline import respostas as resp
from pipeline.analise import analisar
from pipeline.exportar import chave_fornecedor, chave_parlamentar, exportar
from pipeline.normalizacao.esquema import DDL
from tests.fabrica import despesa, despesas

REFEICAO = "Fornecimento de alimentação do parlamentar"


@pytest.fixture
def con():
    con = db.conectar(":memory:")
    con.execute(DDL)
    df = despesas(
        despesa(id="a", categoria=REFEICAO, valor=500.0, fornecedor_nome="RESTAURANTE"),
        despesa(id="b", categoria=REFEICAO, valor=50.0, fornecedor_nome="RESTAURANTE"),
        despesa(id="c", casa="senado", parlamentar_id="nome:FULANO DE TAL", valor=80.0,
                fornecedor_cnpj_cpf="12345678901", fornecedor_nome="Pessoa"),
    )  # fmt: skip
    con.register("df", df)
    con.execute("INSERT INTO despesas SELECT * FROM df")
    conf = {"R01_refeicao_alta": {"peso": 1.0, "limite": 250.0, "categorias": [REFEICAO]}}
    analisar(con, conf)
    return con


def test_chaves():
    assert chave_parlamentar("camara", "204379") == "camara-204379"
    assert chave_parlamentar("senado", "nome:FULANO DE TAL") == "senado-fulano-de-tal"
    assert chave_fornecedor("11222333000181", "X") == "11222333000181"
    cpf = chave_fornecedor("12345678901", "Pessoa")
    assert cpf.startswith("f") and "12345678901" not in cpf  # CPF não vai para a URL


def test_exporta_jsons_do_site(con, tmp_path):
    pasta_resp = tmp_path / "respostas"
    codigo = db.escalar(con, "SELECT codigo FROM alertas")
    resp.registrar(
        pasta_resp,
        resp.Resposta(alerta=codigo, recebida_em=date(2026, 10, 20), autor="Gabinete",
                      texto='Nota "fiscal" correta.\n\nSegundo parágrafo.'),
    )  # fmt: skip
    config = cfg.carregar_config()
    agora = datetime(2026, 10, 22, 12, tzinfo=UTC)
    resumo = exportar(con, config, tmp_path / "data", pasta_resp, agora)
    assert resumo == {"alertas": 1, "parlamentares": 2, "fornecedores": 1}

    ler = lambda nome: json.loads((tmp_path / "data" / f"{nome}.json").read_text("utf-8"))  # noqa: E731
    alerta = ler("alertas")[0]
    assert alerta["codigo"] == codigo
    assert alerta["regra_nome"] == "Refeição acima do limite"
    assert alerta["fornecedor_documento"] == "11.222.333/0001-81"
    assert alerta["respostas"][0]["texto"] == 'Nota "fiscal" correta.\n\nSegundo parágrafo.'

    meta = ler("meta")
    assert meta["atualizado_em"] == "2026-10-22T09:00:00-03:00"
    assert meta["aviso"].startswith("Atipicidade estatística não é prova")
    assert meta["por_regra"]["R01_refeicao_alta"] == 1
    assert meta["respostas"] == 1

    parl = {p["chave"]: p for p in ler("parlamentares")}
    assert parl["camara-1"]["total"] == 550.0 and parl["camara-1"]["alertas"] == [codigo]
    assert parl["senado-fulano-de-tal"]["alertas"] == []

    regras = ler("regras")
    assert len(regras) == 5 and "def aplicar" in regras[0]["codigo_fonte"]


def test_respostas_validadas(tmp_path):
    with pytest.raises(ValueError):
        resp.Resposta(
            alerta="X-1", recebida_em=date(2026, 1, 1), autor="Ana", texto="curto demais?"
        )
    r = resp.Resposta(
        alerta="A-2026-00001",
        recebida_em=date(2026, 1, 1),
        autor="Ana",
        texto="Texto suficiente.",
        documento="https://exemplo.test/nota.pdf",
    )
    p1 = resp.registrar(tmp_path, r)
    p2 = resp.registrar(tmp_path, r)
    assert (p1.name, p2.name) == ("A-2026-00001-1.toml", "A-2026-00001-2.toml")
    assert resp.carregar(tmp_path) == [r, r]
