"""Testa a afinidade Win32 e a aplicação da preferência em todas as janelas."""

from pathlib import Path
from unittest import mock

from mascot import platform_windows


class _Widget:
    def winId(self):
        return 1234


def main():
    set_affinity = mock.Mock(return_value=1)
    user32 = mock.Mock(SetWindowDisplayAffinity=set_affinity)
    with mock.patch.object(platform_windows.ctypes, "windll", create=True) as windll:
        windll.user32 = user32
        assert platform_windows.aplicar_protecao_captura(_Widget(), True) is True
        set_affinity.assert_called_with(1234, platform_windows.WDA_EXCLUDEFROMCAPTURE)
        assert platform_windows.aplicar_protecao_captura(_Widget(), False) is True
        set_affinity.assert_called_with(1234, platform_windows.WDA_NONE)
    raiz = Path(__file__).resolve().parent.parent
    for arquivo in ("menu_sao.py", "modal_configuracoes.py"):
        fonte = (raiz / "mascot" / arquivo).read_text(encoding="utf-8")
        assert "QTimer.singleShot(0" in fonte
        assert "aplicar_protecao_captura(" in fonte
    print("OK: proteção de captura ativa/inativa e fallback validados")


if __name__ == "__main__":
    main()
