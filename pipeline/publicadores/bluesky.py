"""Bluesky via biblioteca `atproto`, com link clicável e card do alerta."""

import os

from pipeline.publicadores.base import AlertaPublicavel, Publicador


class PublicadorBluesky(Publicador):
    rede = "bluesky"
    limite_caracteres = 300  # grafemas

    def __init__(self, nome_site: str):
        self.nome_site = nome_site
        self._cliente = None

    def sufixo(self, alerta: AlertaPublicavel) -> str:
        return f" {alerta.url}"

    def configurado(self) -> bool:
        return bool(os.environ.get("BLUESKY_HANDLE") and os.environ.get("BLUESKY_APP_PASSWORD"))

    def _conectar(self):
        if self._cliente is None:
            from atproto import Client

            self._cliente = Client()
            self._cliente.login(os.environ["BLUESKY_HANDLE"], os.environ["BLUESKY_APP_PASSWORD"])
        return self._cliente

    def enviar(self, texto: str, alerta: AlertaPublicavel) -> tuple[str, str | None]:
        from atproto import client_utils, models

        corpo = texto.removesuffix(self.sufixo(alerta))
        conteudo = client_utils.TextBuilder().text(corpo + " ").link(alerta.url, alerta.url)
        card = models.AppBskyEmbedExternal.Main(
            external=models.AppBskyEmbedExternal.External(
                uri=alerta.url,
                title=f"{alerta.codigo} — {alerta.regra_nome}",
                description=f"{self.nome_site}: detalhes, documento oficial e direito de resposta.",
            )
        )
        cliente = self._conectar()
        post = cliente.send_post(text=conteudo, embed=card)
        rkey = post.uri.rsplit("/", 1)[-1]
        return post.uri, f"https://bsky.app/profile/{cliente.me.handle}/post/{rkey}"
