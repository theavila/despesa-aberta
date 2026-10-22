from datetime import date

import httpx
import polars as pl
import pytest

from pipeline import config as cfg
from pipeline import db
from pipeline.analise import analisar, gravar_alertas
from pipeline.coletores import cnpj
from pipeline.normalizacao.esquema import DDL
from pipeline.regras import REGRAS, aplicar_regras
from pipeline.regras.base import Contexto
from tests.fabrica import despesa, despesas

REFEICAO = "Fornecimento de alimentação do parlamentar"


@pytest.fixture
def con():
    con = db.conectar(":memory:")
    con.execute(DDL)
    return con


def _gravar_despesas(con, df: pl.DataFrame) -> None:
    con.execute("DELETE FROM despesas")
    con.register("df", df)
    con.execute("INSERT INTO despesas SELECT * FROM df")
    con.unregister("df")


def test_regras_tem_metadados_completos():
    ids = [r.id for r in REGRAS]
    assert ids == sorted(ids) and len(set(ids)) == 5
    for regra in REGRAS:
        assert regra.nome and len(regra.descricao) > 80
    # Toda regra configurada no config.toml existe, e vice-versa.
    assert set(cfg.carregar_config()["regras"]) == set(ids)


def test_nenhuma_regra_usa_partido_uf_ou_nome():
    """Embaralhar partido, UF e nome não pode mudar nenhum alerta."""
    conf = cfg.carregar_config()["regras"]
    linhas = [
        despesa(id=f"r{i}", categoria=REFEICAO, valor=100.0 + i * 5, data=date(2026, 3, 1 + i % 28))
        for i in range(150)
    ]
    original = despesas(*linhas)
    embaralhado = original.with_columns(
        pl.col("partido").shuffle(seed=1).str.reverse(),
        pl.col("uf").str.reverse(),
        pl.col("parlamentar_nome").str.to_uppercase(),
    )
    a = aplicar_regras(original, conf, Contexto()).sort("regra_id", "despesa_id")
    b = aplicar_regras(embaralhado, conf, Contexto()).sort("regra_id", "despesa_id")
    assert not a.is_empty()
    assert a.equals(b)


def test_score_e_peso_vezes_intensidade():
    df = despesas(despesa(id="x", categoria=REFEICAO, valor=750.0))
    conf = {"R01_refeicao_alta": {"peso": 0.5, "limite": 250.0, "categorias": [REFEICAO]}}
    r = aplicar_regras(df, conf, Contexto())
    assert r.select("regra_id", "despesa_id", "score").to_dicts() == [
        {"regra_id": "R01_refeicao_alta", "despesa_id": "x", "score": 30}  # 100 × 0,5 × 3/5
    ]


def test_codigos_estaveis_e_alertas_inativos(con):
    conf = {"R01_refeicao_alta": {"peso": 1.0, "limite": 250.0, "categorias": [REFEICAO]}}
    _gravar_despesas(
        con,
        despesas(
            despesa(id="b", categoria=REFEICAO, valor=300.0, data=date(2026, 2, 1)),
            despesa(id="a", categoria=REFEICAO, valor=400.0, data=date(2026, 1, 5)),
            despesa(id="c", categoria=REFEICAO, valor=500.0, data=date(2025, 12, 1)),
        ),
    )
    assert analisar(con, conf) == {"novos": 3, "ativos": 3, "inativos": 0}
    codigos = dict(con.execute("SELECT despesa_id, codigo FROM alertas").fetchall())
    # Numeração por ano da competência, em ordem cronológica.
    assert codigos == {"a": "A-2026-00001", "b": "A-2026-00002", "c": "A-2025-00001"}

    # Reanálise sem mudança: nada novo, mesmos códigos.
    assert analisar(con, conf) == {"novos": 0, "ativos": 3, "inativos": 0}

    # Despesa "a" corrigida na fonte (não dispara mais) e nova despesa "d".
    _gravar_despesas(
        con,
        despesas(
            despesa(id="a", categoria=REFEICAO, valor=100.0, data=date(2026, 1, 5)),
            despesa(id="b", categoria=REFEICAO, valor=300.0, data=date(2026, 2, 1)),
            despesa(id="c", categoria=REFEICAO, valor=500.0, data=date(2025, 12, 1)),
            despesa(id="d", categoria=REFEICAO, valor=600.0, data=date(2026, 3, 1)),
        ),
    )
    assert analisar(con, conf) == {"novos": 1, "ativos": 3, "inativos": 1}
    linhas = dict(
        (d, (c, a))
        for d, c, a in con.execute("SELECT despesa_id, codigo, ativo FROM alertas").fetchall()
    )
    assert linhas["a"] == ("A-2026-00001", False)
    assert linhas["d"] == ("A-2026-00003", True)  # código 00001 nunca é reutilizado


def test_gravar_sem_candidatos(con):
    vazio = aplicar_regras(despesas(), {}, Contexto())
    assert gravar_alertas(con, vazio) == {"novos": 0, "ativos": 0, "inativos": 0}


def test_cache_de_cnpj_com_prioridade_e_limite_de_taxa(con):
    _gravar_despesas(
        con,
        despesas(
            despesa(fornecedor_cnpj_cpf="11111111000111", valor=10.0),
            despesa(fornecedor_cnpj_cpf="22222222000122", valor=900.0),
            despesa(fornecedor_cnpj_cpf="33333333000133", valor=500.0),
            despesa(fornecedor_cnpj_cpf="12345678901", valor=5000.0),  # CPF: não consulta
        ),
    )
    pedidos = []

    def responder(request: httpx.Request) -> httpx.Response:
        numero = request.url.path.rsplit("/", 1)[-1]
        pedidos.append(numero)
        if numero == "33333333000133":
            return httpx.Response(404)
        return httpx.Response(
            200,
            json={
                "descricao_situacao_cadastral": "BAIXADA",
                "data_situacao_cadastral": "2020-01-31",
                "data_inicio_atividade": "2001-05-02",
                "razao_social": "EMPRESA",
            },
        )

    esperas = []
    config_cnpj = {
        "url": "https://api.test/cnpj/{cnpj}",
        "intervalo_segundos": 1.5,
        "max_consultas_por_execucao": 2,
        "validade_dias": 30,
    }
    cliente = httpx.Client(transport=httpx.MockTransport(responder))
    hoje = date(2026, 10, 1)
    assert cnpj.atualizar_cache(con, cliente, config_cnpj, hoje=hoje, dormir=esperas.append) == 2
    assert pedidos == ["22222222000122", "33333333000133"]  # maior valor primeiro
    assert esperas == [1.5]
    # 404 fica no cache com erro e não volta a ser consultado; falta só o de menor valor.
    assert cnpj.atualizar_cache(con, cliente, config_cnpj, hoje=hoje, dormir=esperas.append) == 1
    assert pedidos[-1] == "11111111000111"
    carregado = cnpj.carregar(con).sort("cnpj")
    assert carregado["cnpj"].to_list() == ["11111111000111", "22222222000122"]
    assert carregado["data_situacao"][0] == date(2020, 1, 31)
