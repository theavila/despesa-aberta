from datetime import date

from pipeline.regras.base import Contexto
from pipeline.regras.r02_duplicidade import REGRA
from tests.fabrica import despesa, despesas

PARAMS = {"valor_minimo": 100.0, "categorias_excluidas": ["Hospedagem"]}
DIA = date(2026, 4, 2)


def test_marca_repeticoes_mas_nao_a_primeira():
    df = despesas(
        despesa(id="a", valor=300.0, data=DIA),
        despesa(id="b", valor=300.0, data=DIA),
        despesa(id="c", valor=300.0, data=DIA),
    )
    r = REGRA.aplicar(df, PARAMS, Contexto()).sort("despesa_id")
    assert r["despesa_id"].to_list() == ["b", "c"]
    assert r["intensidade"].to_list() == [1.0, 1.0]
    assert r["detalhe"][0] == (
        "Há 3 despesas deste parlamentar com o mesmo fornecedor, o mesmo valor "
        "(R$ 300,00) e a mesma data (02/04/2026)."
    )


def test_qualquer_diferenca_desfaz_a_duplicidade():
    df = despesas(
        despesa(id="a", valor=300.0, data=DIA),
        despesa(id="b", valor=300.01, data=DIA),
        despesa(id="c", valor=300.0, data=date(2026, 4, 3)),
        despesa(id="d", valor=300.0, data=DIA, parlamentar_id="2"),
        despesa(id="e", valor=300.0, data=DIA, fornecedor_cnpj_cpf="99888777000166"),
    )
    assert REGRA.aplicar(df, PARAMS, Contexto()).is_empty()


def test_sem_cnpj_compara_pelo_nome_do_fornecedor():
    df = despesas(
        despesa(id="a", valor=150.0, data=DIA, fornecedor_cnpj_cpf=None, fornecedor_nome="Táxi"),
        despesa(id="b", valor=150.0, data=DIA, fornecedor_cnpj_cpf=None, fornecedor_nome="TÁXI"),
    )
    assert REGRA.aplicar(df, PARAMS, Contexto())["despesa_id"].to_list() == ["b"]


def test_ignora_valor_baixo_sem_data_e_categoria_excluida():
    df = despesas(
        despesa(id="a", valor=50.0, data=DIA),
        despesa(id="b", valor=50.0, data=DIA),
        despesa(id="c", valor=300.0, data=None),
        despesa(id="d", valor=300.0, data=None),
        despesa(id="e", valor=300.0, data=DIA, categoria="HOSPEDAGEM"),
        despesa(id="f", valor=300.0, data=DIA, categoria="HOSPEDAGEM"),
    )
    assert REGRA.aplicar(df, PARAMS, Contexto()).is_empty()
