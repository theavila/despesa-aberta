import json
import sys
import types
from datetime import UTC, date, datetime

import httpx
import pytest

from pipeline import db, publicacao
from pipeline.normalizacao.esquema import DDL
from pipeline.publicadores.base import AVISO, AlertaPublicavel, Publicador, texto_base
from pipeline.publicadores.bluesky import PublicadorBluesky
from pipeline.publicadores.mastodon import PublicadorMastodon
from pipeline.publicadores.x import PublicadorX, assinatura_oauth1, cabecalho_oauth1, tamanho_x
from tests.fabrica import despesa, despesas

URL = "https://despesa-aberta.test/alerta/A-2026-00123/"


def _alerta(**campos) -> AlertaPublicavel:
    base = {
        "codigo": "A-2026-00123",
        "casa": "camara",
        "parlamentar_nome": "Fulana de Tal",
        "partido": "ABC",
        "uf": "SP",
        "valor": 1234.5,
        "categoria": "Fornecimento de alimentação do parlamentar",
        "data": date(2026, 3, 9),
        "fornecedor_nome": "RESTAURANTE EXEMPLO LTDA",
        "regra_nome": "Refeição acima do limite",
        "score": 60,
        "url": URL,
    }
    return AlertaPublicavel(**(base | campos))


SENADO_LONGO = _alerta(
    casa="senado",
    partido=None,
    uf="DF",
    categoria=(
        "Contratação de consultorias, assessorias, pesquisas, trabalhos técnicos e outros "
        "serviços de apoio ao exercício do mandato parlamentar"
    ),
    fornecedor_nome="EMPRESA DE CONSULTORIA COM UM NOME MUITO MAS MUITO COMPRIDO MESMO LTDA",
    parlamentar_nome="Nome Bastante Comprido de Senadora Exemplo",
)


def test_modelo_unico_de_texto():
    assert texto_base(_alerta()) == (
        "[Câmara] Dep. Fulana de Tal (ABC-SP) — R$ 1.234,50 em Fornecimento de alimentação "
        "do parlamentar, 09/03/2026, fornecedor RESTAURANTE EXEMPLO LTDA. Regra: Refeição "
        "acima do limite. Atípico ≠ irregular. Cód. A-2026-00123"
    )
    assert texto_base(SENADO_LONGO).startswith("[Senado] Sen. Nome Bastante")
    assert "(DF)" in texto_base(SENADO_LONGO)  # sem partido no cadastro


@pytest.mark.parametrize("texto", ["escândalo", "absurdo", "roubo", "desvio", "fraude", "corrup"])
def test_linguagem_neutra(texto):
    for alerta in (_alerta(), SENADO_LONGO):
        for publicador in (PublicadorX("Despesa Aberta"), PublicadorBluesky("Despesa Aberta")):
            assert texto not in publicador.texto(alerta).lower()


def test_x_sem_link_e_dentro_do_limite():
    px = PublicadorX("Despesa Aberta")
    for alerta in (_alerta(), SENADO_LONGO):
        texto = px.texto(alerta)
        assert "http" not in texto
        assert "A-2026-00123" in texto and texto.endswith("Busque o código no site Despesa Aberta.")
        assert tamanho_x(texto) <= 280
    assert "…" in px.texto(SENADO_LONGO)  # categoria e fornecedor encurtados
    assert "…." not in px.texto(SENADO_LONGO)
    assert "LTDA.. Regra" not in texto_base(_alerta(fornecedor_nome="EXEMPLO LTDA."))


def test_tamanho_ponderado_do_x():
    assert tamanho_x("ação — ok") == 9
    assert tamanho_x("≠") == 2


def test_bluesky_e_mastodon_com_link():
    bsky = PublicadorBluesky("Despesa Aberta").texto(SENADO_LONGO)
    assert bsky.endswith(URL) and len(bsky) <= 300
    masto = PublicadorMastodon("Despesa Aberta")
    texto = masto.texto(SENADO_LONGO)
    assert AVISO in texto and texto.endswith(URL)
    assert masto.tamanho(texto) <= 500


def test_assinatura_oauth1_exemplo_da_documentacao():
    """Exemplo oficial de 'Creating a signature' da documentação do Twitter/X."""
    params = {
        "status": "Hello Ladies + Gentlemen, a signed OAuth request!",
        "include_entities": "true",
        "oauth_consumer_key": "xvz1evFS4wEEPTGEFPHBog",
        "oauth_nonce": "kYjzVBB8Y0ZFabxSWbWovY3uYSQ2pTgmZeNu2VS4cg",
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": "1318622958",
        "oauth_token": "370773112-GmHxMAgYyLbNEtIKZeRNFsMKPR9EyMZeS9weJAEb",
        "oauth_version": "1.0",
    }
    assinatura = assinatura_oauth1(
        "POST",
        "https://api.twitter.com/1.1/statuses/update.json",
        params,
        "kAcSOqF21Fu85e7zjz7ZN2U4ZRhfV3WpwPAoE3Z7kBw",
        "LswwdoUaIvS8ltyTt5jkRh4J50vUPVVHtR2YPi5kE",
    )
    assert assinatura == "hCtSmYh+iHYCEqBWrE7C7hYmtUk="


def test_x_envia_post_assinado(monkeypatch):
    for var in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"):
        monkeypatch.setenv(var, f"valor-{var}")
    pedidos = []

    def responder(request: httpx.Request) -> httpx.Response:
        pedidos.append(request)
        return httpx.Response(201, json={"data": {"id": "999", "text": "..."}})

    cliente = httpx.Client(transport=httpx.MockTransport(responder))
    px = PublicadorX("Despesa Aberta", cliente=cliente)
    assert px.configurado()
    r = px.publicar(_alerta(), dry_run=False)
    assert r.sucesso and r.id_externo == "999" and r.url.endswith("/999")
    assert str(pedidos[0].url) == "https://api.x.com/2/tweets"
    assert (
        pedidos[0].headers["Authorization"].startswith('OAuth oauth_consumer_key="valor-X_API_KEY"')
    )
    assert json.loads(pedidos[0].content) == {"text": px.texto(_alerta())}


def test_x_erro_traz_o_motivo(monkeypatch):
    for var in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"):
        monkeypatch.setenv(var, "v")
    cliente = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(401, json={"title": "Unauthorized"}))
    )
    r = PublicadorX("Despesa Aberta", cliente=cliente).publicar(_alerta(), dry_run=False)
    assert not r.sucesso and "401" in r.erro and "Unauthorized" in r.erro


def test_cabecalho_oauth1_tem_todos_os_campos():
    cab = cabecalho_oauth1("POST", "https://api.x.com/2/tweets", "k", "s", "t", "ts", "n", "1")
    for campo in ("oauth_consumer_key", "oauth_nonce", "oauth_signature", "oauth_timestamp"):
        assert f'{campo}="' in cab


def test_mastodon_envia_com_biblioteca(monkeypatch):
    monkeypatch.setenv("MASTODON_API_BASE_URL", "https://masto.test")
    monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "token")
    enviados = []

    class FakeMastodon:
        def __init__(self, access_token, api_base_url):
            assert (access_token, api_base_url) == ("token", "https://masto.test")

        def status_post(self, texto, **kwargs):
            enviados.append((texto, kwargs))
            return {"id": 42, "url": "https://masto.test/@despesaaberta/42"}

    monkeypatch.setitem(sys.modules, "mastodon", types.SimpleNamespace(Mastodon=FakeMastodon))
    r = PublicadorMastodon("Despesa Aberta").publicar(_alerta(), dry_run=False)
    assert (r.sucesso, r.id_externo) == (True, "42")
    assert enviados[0][1]["visibility"] == "public"


class PublicadorFalso(Publicador):
    limite_caracteres = 1000

    def __init__(self, rede: str, falhar: bool = False):
        self.rede = rede
        self.falhar = falhar
        self.enviados: list[str] = []

    def configurado(self) -> bool:
        return True

    def enviar(self, texto, alerta):
        if self.falhar:
            raise RuntimeError("rede fora do ar")
        self.enviados.append(alerta.codigo)
        return f"id-{alerta.codigo}", None


CONFIG = {
    "site": {"url": "https://despesa-aberta.test", "nome": "Despesa Aberta"},
    "publicacao": {"fuso": "America/Sao_Paulo", "por_execucao": 2, "limite_diario": {"x": 3}},
}


@pytest.fixture
def con():
    con = db.conectar(":memory:")
    con.execute(DDL)
    df = despesas(*(despesa(id=f"d{i}", valor=100.0 * i) for i in range(1, 6)))
    con.register("df", df)
    con.execute("INSERT INTO despesas SELECT * FROM df")
    agora = db.agora()
    for i, score in zip(range(1, 6), [10, 90, 50, 90, 70], strict=True):
        con.execute(
            "INSERT INTO alertas VALUES (?, 'R01_refeicao_alta', ?, ?, 'x', ?, ?, ?)",
            [f"A-2026-0000{i}", f"d{i}", score, i != 5, agora, agora],
        )
    return con


def test_dry_run_e_o_padrao(monkeypatch):
    monkeypatch.delenv("PUBLICAR", raising=False)
    assert not publicacao.publicacao_ativada()
    monkeypatch.setenv("PUBLICAR", "true")
    assert not publicacao.publicacao_ativada()
    monkeypatch.setenv("PUBLICAR", "1")
    assert publicacao.publicacao_ativada()


def test_fila_por_score_sem_inativos(con):
    codigos = [a.codigo for a in publicacao.fila(con, "x", 10, "https://despesa-aberta.test")]
    # score 90 (valor 400) > 90 (valor 200) > 50 > 10; A-2026-00005 está inativo
    assert codigos == ["A-2026-00004", "A-2026-00002", "A-2026-00003", "A-2026-00001"]
    assert publicacao.fila(con, "x", 1, "https://s.test")[0].url == (
        "https://s.test/alerta/A-2026-00004/"
    )


def test_dry_run_nao_envia_nem_grava(con):
    falso = PublicadorFalso("x")
    resultados = publicacao.publicar(con, [falso], CONFIG, dry_run=True)
    assert [r.codigo for r in resultados] == ["A-2026-00004", "A-2026-00002"]
    assert all(r.dry_run for r in resultados)
    assert falso.enviados == []
    assert db.escalar(con, "SELECT count(*) FROM publicacoes") == 0


def test_nao_repete_e_respeita_limite_diario(con):
    falso = PublicadorFalso("x")
    publicacao.publicar(con, [falso], CONFIG, dry_run=False)
    publicacao.publicar(con, [falso], CONFIG, dry_run=False)
    publicacao.publicar(con, [falso], CONFIG, dry_run=False)
    # 2 + 1 (limite diário 3) + 0; nunca o mesmo alerta duas vezes
    assert falso.enviados == ["A-2026-00004", "A-2026-00002", "A-2026-00003"]
    assert db.escalar(con, "SELECT count(*) FROM publicacoes WHERE sucesso") == 3
    # No dia seguinte (horário de Brasília), a cota volta.
    amanha = datetime.now(UTC).replace(hour=12) + (datetime(2, 1, 2) - datetime(2, 1, 1))
    publicacao.publicar(con, [falso], CONFIG, dry_run=False, agora=amanha)
    assert falso.enviados[-1] == "A-2026-00001"


def test_falha_fica_registrada_e_volta_para_a_fila(con):
    publicacao.publicar(con, [PublicadorFalso("x", falhar=True)], CONFIG, dry_run=False, limite=1)
    erro = con.execute("SELECT codigo, sucesso, erro FROM publicacoes").fetchall()
    assert erro == [("A-2026-00004", False, "rede fora do ar")]
    assert publicacao.fila(con, "x", 1, "https://s.test")[0].codigo == "A-2026-00004"


def test_rede_sem_credenciais_e_ignorada_na_publicacao_real(con, monkeypatch):
    for var in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"):
        monkeypatch.delenv(var, raising=False)
    assert publicacao.publicar(con, [PublicadorX("Despesa Aberta")], CONFIG, dry_run=False) == []
