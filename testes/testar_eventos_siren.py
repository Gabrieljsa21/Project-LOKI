"""Valida o schema recebido sem abrir socket ou janela."""

from mascot.playback_events import validar_evento


def main():
    valido = {
        "schema": "siren.playback.v1",
        "type": "track_started",
        "session_id": "sessao",
        "track_id": "faixa",
        "sequence": 1,
        "track": {"titulo": "Música", "artista": "Artista"},
    }
    assert validar_evento(valido) is valido
    assert validar_evento({**valido, "schema": "outro"}) is None
    assert validar_evento({**valido, "type": "executar_codigo"}) is None
    assert validar_evento({**valido, "sequence": "1"}) is None
    # JSON aceita listas, mas elas não podem virar chaves do controle de
    # sequência do receptor.
    assert validar_evento({**valido, "session_id": ["sessao"]}) is None
    print("OK: schema SIREN playback v1 validado no LOKI")


if __name__ == "__main__":
    main()
