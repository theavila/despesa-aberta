from pipeline.regras.base import Contexto
from pipeline.regras.r01_refeicao_alta import REGRA
from tests.fabrica import despesa, despesas

PARAMS = {"limite": 250.0, "categorias": ["Fornecimento de alimentação do parlamentar"]}
REFEICAO = "FORNECIMENTO DE ALIMENTAÇÃO DO PARLAMENTAR"  # caixa diferente da configuração


def test_marca_refeicao_acima_do_limite():
    df = despesas(
        despesa(id="alta", categoria=REFEICAO, valor=500.0),
        despesa(id="no_limite", categoria=REFEICAO, valor=250.0),
        despesa(id="outra_categoria", categoria="Combustíveis e lubrificantes", valor=900.0),
    )
    r = REGRA.aplicar(df, PARAMS, Contexto())
    assert r["despesa_id"].to_list() == ["alta"]
    assert r["intensidade"][0] == 0.4  # 2 vezes o limite, teto em 5 vezes
    assert r["detalhe"][0] == (
        "Refeição de R$ 500,00; o limite configurado é R$ 250,00 (2,0 vezes o limite)."
    )


def test_intensidade_tem_teto():
    df = despesas(despesa(categoria=REFEICAO, valor=10_000.0))
    assert REGRA.aplicar(df, PARAMS, Contexto())["intensidade"][0] == 1.0


def test_mesma_regra_para_todos():
    """Partido, UF e nome não mudam o resultado."""
    a = despesas(despesa(id="x", categoria=REFEICAO, valor=300.0, partido="A", uf="SP"))
    b = despesas(
        despesa(id="x", categoria=REFEICAO, valor=300.0, partido="B", uf="RJ", parlamentar_nome="Z")
    )
    assert REGRA.aplicar(a, PARAMS, Contexto()).equals(REGRA.aplicar(b, PARAMS, Contexto()))
