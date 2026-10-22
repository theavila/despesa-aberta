"""Cliente HTTP com timeout, User-Agent do projeto e retry com backoff exponencial."""

import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

log = logging.getLogger(__name__)

STATUS_TRANSITORIOS = {429, 500, 502, 503, 504}


class ErroDeColeta(RuntimeError):
    pass


def criar_cliente(config_coleta: dict[str, Any], **kwargs: Any) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": config_coleta["user_agent"]},
        timeout=config_coleta["timeout_segundos"],
        follow_redirects=True,
        **kwargs,
    )


def obter(
    cliente: httpx.Client,
    url: str,
    *,
    tentativas: int = 5,
    backoff_base: float = 2.0,
    dormir: Callable[[float], None] = time.sleep,
    **kwargs: Any,
) -> httpx.Response:
    """GET com retry em erros de rede e respostas transitórias (429/5xx).

    A espera entre tentativas é `backoff_base * 2**n` segundos.
    """
    for n in range(tentativas):
        try:
            resposta = cliente.get(url, **kwargs)
        except httpx.TransportError as erro:
            motivo = f"{type(erro).__name__}: {erro}"
        else:
            if resposta.status_code not in STATUS_TRANSITORIOS:
                resposta.raise_for_status()
                return resposta
            motivo = f"HTTP {resposta.status_code}"
        if n + 1 < tentativas:
            espera = backoff_base * 2**n
            log.warning("Falha em %s (%s); nova tentativa em %.0fs", url, motivo, espera)
            dormir(espera)
    raise ErroDeColeta(f"{url} falhou após {tentativas} tentativas ({motivo})")
