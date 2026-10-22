"""Mastodon via biblioteca `Mastodon.py`, com link e o aviso completo (cabe em 500)."""

import os
import re

from pipeline.publicadores.base import AVISO, AlertaPublicavel, Publicador

TAMANHO_LINK = 23  # o Mastodon conta qualquer URL como 23 caracteres


class PublicadorMastodon(Publicador):
    rede = "mastodon"
    limite_caracteres = 500

    def __init__(self, nome_site: str):
        self.nome_site = nome_site

    def sufixo(self, alerta: AlertaPublicavel) -> str:
        return f"\n\n{AVISO}\n{alerta.url}"

    def tamanho(self, texto: str) -> int:
        return len(re.sub(r"https?://\S+", "x" * TAMANHO_LINK, texto))

    def configurado(self) -> bool:
        return bool(
            os.environ.get("MASTODON_API_BASE_URL") and os.environ.get("MASTODON_ACCESS_TOKEN")
        )

    def enviar(self, texto: str, alerta: AlertaPublicavel) -> tuple[str, str | None]:
        from mastodon import Mastodon

        cliente = Mastodon(
            access_token=os.environ["MASTODON_ACCESS_TOKEN"],
            api_base_url=os.environ["MASTODON_API_BASE_URL"],
        )
        status = cliente.status_post(texto, visibility="public", language="pt")
        return str(status["id"]), status.get("url")
