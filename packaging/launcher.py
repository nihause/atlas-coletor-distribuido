"""Entrada do pacote: GUI por padrão; CLI existente preservada via lançador próprio."""
import sys

if sys.argv[1:2] == ["--diagnostico-instalacao"] and len(sys.argv)==3:
    from pathlib import Path
    from atlas_worker.installation_probe import run
    run(Path(sys.argv[2]))
    raise SystemExit(0)
elif sys.argv[1:2] == ["--install-update"]:
    from atlas_worker.installer import main
    raise SystemExit(main(sys.argv[2:]))
elif "--cli" in sys.argv[1:2]:
    from atlas_worker.main import cli
    cli(sys.argv[2:])
else:
    from atlas_worker.gui.app import main
    raise SystemExit(main())
