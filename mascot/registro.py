"""Log no padrão do ecossistema (CLAUDE.md global, seção "Logs"; 2026-11-14).

`%LOCALAPPDATA%\\Ecossistema\\<PROJETO>\\Logs\\AAAA-MM-DD.log`, fora do
repositório, um arquivo por dia e 30 dias guardados. Os módulos usam
`logging.getLogger(__name__)`; só o ponto de entrada chama `configurar`.
Com `pythonw` não há console: `print`, stderr e exceções não tratadas
também vão para o log.

Modelo de referência: copiar este arquivo como está em cada projeto
(trocando só o nome passado a `configurar`), sem pacote compartilhado.
"""

import datetime
import logging
import os
import sys
import threading
from pathlib import Path

DIAS_GUARDAR = 30
FORMATO = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def pasta_logs(projeto: str) -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Ecossistema" / projeto / "Logs"


class ArquivoDoDia(logging.Handler):
    """Grava em `<pasta>/AAAA-MM-DD.log`, trocando de arquivo na virada do dia."""

    def __init__(self, pasta: Path):
        super().__init__()
        self.pasta = pasta
        self.dia: str | None = None
        self.arquivo = None

    def emit(self, registro: logging.LogRecord) -> None:
        try:
            hoje = datetime.date.today().isoformat()
            if hoje != self.dia:
                if self.arquivo:
                    self.arquivo.close()
                self.arquivo = open(self.pasta / f"{hoje}.log", "a", encoding="utf-8")  # noqa: SIM115
                self.dia = hoje
            self.arquivo.write(self.format(registro) + "\n")
            self.arquivo.flush()
        except Exception:
            self.handleError(registro)


class _SaidaParaLog:
    """`sys.stdout`/`sys.stderr` que viram linhas de log (o `print` não se perde).

    Trava de reentrada: se o próprio log falhar e o `logging` escrever o erro
    no stderr, essa escrita é descartada em vez de virar outra linha de log
    (sem a trava, a CLIO 0.18 entrou num laço infinito).

    O `print("a", "b")` chega em pedaços ("a", " ", "b", "\\n"): cada thread
    acumula até a quebra de linha e grava a linha inteira (ideia da GAIA)."""

    _dentro = threading.local()

    def __init__(self, nome: str, nivel: int):
        self.log = logging.getLogger(nome)
        self.nivel = nivel
        self._pendente = threading.local()

    def _gravar(self, linhas: list[str]) -> None:
        if getattr(self._dentro, "ativo", False):
            return
        self._dentro.ativo = True
        try:
            for linha in linhas:
                if linha.strip():
                    self.log.log(self.nivel, linha.rstrip())
        finally:
            self._dentro.ativo = False

    def write(self, texto: str) -> int:
        if getattr(self._dentro, "ativo", False):
            return len(texto)
        *completas, resto = (getattr(self._pendente, "texto", "") + texto).split("\n")
        self._pendente.texto = resto
        self._gravar(completas)
        return len(texto)

    def flush(self) -> None:
        resto = getattr(self._pendente, "texto", "")
        self._pendente.texto = ""
        self._gravar([resto])

    def isatty(self) -> bool:
        return False


def limpar(pasta: Path, dias: int = DIAS_GUARDAR, hoje: datetime.date | None = None) -> int:
    """Apaga os `AAAA-MM-DD.log` com mais de `dias`; outros arquivos ficam."""
    limite = (hoje or datetime.date.today()) - datetime.timedelta(days=dias)
    apagados = 0
    for arquivo in pasta.glob("*.log"):
        try:
            if datetime.date.fromisoformat(arquivo.stem) < limite:
                arquivo.unlink()
                apagados += 1
        except (ValueError, OSError):
            continue
    return apagados


def configurar(projeto: str, nivel: int = logging.INFO) -> Path:
    """Liga o log do projeto e devolve a pasta. Chamar uma vez, no ponto de entrada."""
    pasta = pasta_logs(projeto)
    pasta.mkdir(parents=True, exist_ok=True)
    limpar(pasta)
    formato = logging.Formatter(FORMATO)
    raiz = logging.getLogger()
    raiz.setLevel(nivel)
    for antigo in list(raiz.handlers):
        raiz.removeHandler(antigo)
    arquivo = ArquivoDoDia(pasta)
    arquivo.setFormatter(formato)
    raiz.addHandler(arquivo)
    # Só o arquivo, sem console: iniciado pela GAIA (pythonw do uv), o processo
    # parece ter um terminal (isatty verdadeiro), mas escrever nele dá
    # "Função incorreta". Falha de escrita do log também não vira traceback.
    logging.raiseExceptions = False
    logging.getLogger("httpx").setLevel(logging.WARNING)   # uma linha por requisição enche o log
    sys.stdout = _SaidaParaLog("print", logging.INFO)
    sys.stderr = _SaidaParaLog("stderr", logging.WARNING)
    sys.excepthook = lambda tipo, valor, rastro: logging.getLogger("erro").critical(
        "Exceção não tratada", exc_info=(tipo, valor, rastro))
    threading.excepthook = lambda a: logging.getLogger("erro").error(
        "Exceção na thread %s", a.thread.name if a.thread else "?", exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
    return pasta
