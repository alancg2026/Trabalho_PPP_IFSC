"""Compatibilidade: encaminha para o único fluxo de envio do controle."""

from enviar_ppp_controle import main


if __name__ == "__main__":
    raise SystemExit(main())
