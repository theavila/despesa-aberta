"""Interface comum dos publicadores e o modelo único de texto dos posts."""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

from pipeline import formatacao as fmt

log = logging.getLogger(__name__)

AVISO = (
    "Atipicidade estatística não é prova de irregularidade. O parlamentar pode ter justificativa."
)
CASAS = {"camara": ("Câmara", "Dep."), "senado": ("Senado", "Sen.")}
RETICENCIAS = "…"


def credencial(nome: str) -> str:
    """Lê uma credencial do ambiente sem espaços ou quebras de linha copiados por engano."""
    return os.environ.get(nome, "").strip()


@dataclass(frozen=True)
class AlertaPublicavel:
    codigo: str
    casa: str
    parlamentar_nome: str
    partido: str | None
    uf: str | None
    valor: float
    categoria: str
    data: date | None
    fornecedor_nome: str
    regra_nome: str
    score: int
    url: str


@dataclass(frozen=True)
class Resultado:
    rede: str
    codigo: str
    texto: str
    dry_run: bool
    sucesso: bool
    id_externo: str | None = None
    url: str | None = None
    erro: str | None = None


def encurtar(texto: str, maximo: int) -> str:
    """Corta no último espaço antes de `maximo` e acrescenta reticências."""
    if len(texto) <= maximo:
        return texto
    corte = texto[: maximo - 1].rsplit(" ", 1)[0].rstrip(" ,.;-")
    return corte + RETICENCIAS


def _fim_de_frase(texto: str) -> str:
    """Acrescenta ponto final, exceto depois de reticências ou de um ponto já existente."""
    return texto if texto.endswith((RETICENCIAS, ".")) else texto + "."


def texto_base(a: AlertaPublicavel, max_categoria: int = 50, max_fornecedor: int = 40) -> str:
    """Modelo único e neutro, igual para todos os parlamentares."""
    casa, tratamento = CASAS[a.casa]
    filiacao = "-".join(p for p in (a.partido, a.uf) if p)
    filiacao = f" ({filiacao})" if filiacao else ""
    return (
        f"[{casa}] {tratamento} {a.parlamentar_nome}{filiacao} — {fmt.reais(a.valor)} em "
        f"{encurtar(a.categoria, max_categoria)}, {fmt.data_curta(a.data)}, fornecedor "
        f"{_fim_de_frase(encurtar(a.fornecedor_nome, max_fornecedor))} Regra: {a.regra_nome}. "
        f"Atípico ≠ irregular. Cód. {a.codigo}"
    )


class Publicador(ABC):
    rede: str
    limite_caracteres: int

    def sufixo(self, alerta: AlertaPublicavel) -> str:
        """Complemento depois do texto base (link ou instrução de busca)."""
        return ""

    def tamanho(self, texto: str) -> int:
        return len(texto)

    def texto(self, alerta: AlertaPublicavel) -> str:
        """Texto base + sufixo, encurtando categoria e fornecedor até caber no limite."""
        sufixo = self.sufixo(alerta)
        for max_categoria, max_fornecedor in ((50, 40), (35, 30), (25, 20), (18, 15)):
            texto = texto_base(alerta, max_categoria, max_fornecedor) + sufixo
            if self.tamanho(texto) <= self.limite_caracteres:
                return texto
        raise ValueError(f"Texto do alerta {alerta.codigo} não cabe em {self.rede}")

    @abstractmethod
    def configurado(self) -> bool:
        """Se as credenciais necessárias estão nas variáveis de ambiente."""

    @abstractmethod
    def enviar(self, texto: str, alerta: AlertaPublicavel) -> tuple[str, str | None]:
        """Publica de verdade. Devolve (id na rede, url do post)."""

    def publicar(self, alerta: AlertaPublicavel, dry_run: bool = True) -> Resultado:
        texto = self.texto(alerta)
        if dry_run:
            return Resultado(self.rede, alerta.codigo, texto, dry_run=True, sucesso=True)
        try:
            id_externo, url = self.enviar(texto, alerta)
        except Exception as erro:  # a falha de uma rede não interrompe as outras
            log.exception("Falha ao publicar %s em %s", alerta.codigo, self.rede)
            return Resultado(
                self.rede, alerta.codigo, texto, dry_run=False, sucesso=False, erro=str(erro)
            )
        return Resultado(
            self.rede, alerta.codigo, texto, dry_run=False, sucesso=True,
            id_externo=id_externo, url=url,
        )  # fmt: skip
