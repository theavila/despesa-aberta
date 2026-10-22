"""X (antigo Twitter): API v2 `POST /2/tweets` com OAuth 1.0a (user context).

O texto NÃO leva link (posts com link têm tarifa bem mais alta na API); leva o código do
alerta para busca no site.
"""

import base64
import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import quote

import httpx

from pipeline.publicadores.base import AlertaPublicavel, Publicador

URL_TWEETS = "https://api.x.com/2/tweets"
VARIAVEIS = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")


def _pct(texto: str) -> str:
    return quote(texto, safe="~-._")


def assinatura_oauth1(
    metodo: str, url: str, params: dict[str, str], consumer_secret: str, token_secret: str
) -> str:
    """Assinatura HMAC-SHA1 (RFC 5849, seção 3.4)."""
    pares = sorted((_pct(k), _pct(v)) for k, v in params.items())
    normalizados = "&".join(f"{k}={v}" for k, v in pares)
    base = "&".join([metodo.upper(), _pct(url), _pct(normalizados)])
    chave = f"{_pct(consumer_secret)}&{_pct(token_secret)}"
    return base64.b64encode(hmac.new(chave.encode(), base.encode(), hashlib.sha1).digest()).decode()


def cabecalho_oauth1(
    metodo: str,
    url: str,
    consumer_key: str,
    consumer_secret: str,
    token: str,
    token_secret: str,
    nonce: str | None = None,
    timestamp: str | None = None,
) -> str:
    """Cabeçalho `Authorization`. Corpo JSON não entra na assinatura."""
    oauth = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp or str(int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    oauth["oauth_signature"] = assinatura_oauth1(metodo, url, oauth, consumer_secret, token_secret)
    return "OAuth " + ", ".join(f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(oauth.items()))


def tamanho_x(texto: str) -> int:
    """Contagem ponderada do X: a maioria dos caracteres latinos vale 1; os demais, 2."""
    faixas_peso_1 = ((0, 4351), (8192, 8205), (8208, 8223), (8242, 8247))
    return sum(1 if any(a <= ord(c) <= b for a, b in faixas_peso_1) else 2 for c in texto)


class PublicadorX(Publicador):
    rede = "x"
    limite_caracteres = 280

    def __init__(self, nome_site: str, cliente: httpx.Client | None = None):
        self.nome_site = nome_site
        self.cliente = cliente

    def sufixo(self, alerta: AlertaPublicavel) -> str:
        return f". Busque o código no site {self.nome_site}."

    def tamanho(self, texto: str) -> int:
        return tamanho_x(texto)

    def configurado(self) -> bool:
        return all(os.environ.get(v) for v in VARIAVEIS)

    def enviar(self, texto: str, alerta: AlertaPublicavel) -> tuple[str, str | None]:
        key, secret, token, token_secret = (os.environ[v] for v in VARIAVEIS)
        cabecalho = cabecalho_oauth1("POST", URL_TWEETS, key, secret, token, token_secret)
        cliente = self.cliente or httpx.Client(timeout=30)
        resposta = cliente.post(
            URL_TWEETS, json={"text": texto}, headers={"Authorization": cabecalho}
        )
        resposta.raise_for_status()
        id_post = resposta.json()["data"]["id"]
        return id_post, f"https://x.com/i/web/status/{id_post}"
