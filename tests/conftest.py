from pathlib import Path

import httpx
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


def cliente_falso(rotas: dict[str, bytes | httpx.Response]) -> httpx.Client:
    """Cliente HTTP sem rede: responde a partir de um mapa URL -> conteúdo."""

    def responder(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url not in rotas:
            return httpx.Response(404)
        valor = rotas[url]
        return valor if isinstance(valor, httpx.Response) else httpx.Response(200, content=valor)

    return httpx.Client(transport=httpx.MockTransport(responder))
