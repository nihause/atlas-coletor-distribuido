"""Entrada do pacote: GUI por padrão; CLI existente preservada via lançador próprio."""
import sys

if "--cli" in sys.argv[1:2]:
    from atlas_worker.main import cli
    cli(sys.argv[2:])
else:
    from atlas_worker.gui.app import main
    raise SystemExit(main())
