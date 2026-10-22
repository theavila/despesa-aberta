import httpx
import pytest

from pipeline.http import ErroDeColeta, criar_cliente, obter


def _cliente(respostas):
    fila = list(respostas)

    def responder(request):
        item = fila.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return httpx.Client(transport=httpx.MockTransport(responder))


def test_retry_com_backoff_exponencial():
    esperas = []
    cliente = _cliente(
        [httpx.ConnectError("caiu"), httpx.Response(503), httpx.Response(200, text="ok")]
    )
    resposta = obter(cliente, "https://x/a", tentativas=5, backoff_base=2, dormir=esperas.append)
    assert resposta.text == "ok"
    assert esperas == [2, 4]


def test_desiste_apos_esgotar_tentativas():
    esperas = []
    cliente = _cliente([httpx.Response(500)] * 3)
    with pytest.raises(ErroDeColeta, match="3 tentativas"):
        obter(cliente, "https://x/a", tentativas=3, backoff_base=1, dormir=esperas.append)
    assert esperas == [1, 2]


def test_erro_definitivo_nao_repete():
    cliente = _cliente([httpx.Response(404)])
    with pytest.raises(httpx.HTTPStatusError):
        obter(cliente, "https://x/a", dormir=lambda s: None)


def test_cliente_identifica_o_projeto():
    cliente = criar_cliente({"user_agent": "SerenataBot/teste", "timeout_segundos": 7})
    assert cliente.headers["User-Agent"] == "SerenataBot/teste"
    assert cliente.timeout.read == 7


def test_anos_padrao_da_coleta():
    from datetime import date

    from pipeline.cli import anos_padrao

    assert anos_padrao(date(2026, 3, 31)) == [2025, 2026]
    assert anos_padrao(date(2026, 4, 1)) == [2026]
