from pipeline.regras.base import Contexto
from pipeline.regras.r03_outlier_categoria import REGRA
from tests.fabrica import despesa, despesas

PARAMS = {"percentil": 0.99, "amostra_minima": 100}


def _categoria(nome: str, valores: list[float], prefixo: str) -> list[dict]:
    return [despesa(id=f"{prefixo}{i:03d}", categoria=nome, valor=v) for i, v in enumerate(valores)]


def test_marca_valores_acima_do_percentil_da_categoria():
    linhas = _categoria("Telefonia", [100.0] * 99 + [1000.0], "t")
    r = REGRA.aplicar(despesas(*linhas), PARAMS, Contexto())
    assert r["despesa_id"].to_list() == ["t099"]
    # Percentil 99 linear de 99 x 100 e 1 x 1000 = 100 + 0,01 x 900 = 109
    assert "acima do percentil 99 da categoria em 2026 (R$ 109,00" in r["detalhe"][0]
    assert r["intensidade"][0] == 1.0  # 1000 / 109 > 5


def test_percentil_e_por_categoria_e_por_ano():
    linhas = _categoria("Telefonia", [100.0] * 150, "t") + _categoria(
        "Divulgação", [5000.0] * 150, "d"
    )
    # 5000 é comum em Divulgação; não é atípico só porque Telefonia é barata.
    assert REGRA.aplicar(despesas(*linhas), PARAMS, Contexto()).is_empty()


def test_amostra_pequena_nao_e_avaliada():
    linhas = _categoria("Rara", [10.0] * 20 + [10_000.0], "r")
    assert REGRA.aplicar(despesas(*linhas), PARAMS, Contexto()).is_empty()


def test_valores_negativos_nao_entram_no_calculo():
    linhas = _categoria("Telefonia", [100.0] * 120 + [-5000.0], "t")
    assert REGRA.aplicar(despesas(*linhas), PARAMS, Contexto()).is_empty()
