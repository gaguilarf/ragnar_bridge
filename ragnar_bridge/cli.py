import argparse
import asyncio
import logging
import shutil
import sys
from pathlib import Path

from . import __version__
from .bridge import SALIDA_AUTH, ErrorFatal, ejecutar
from .config import Config, ConfigError, cargar, guardar, ruta_por_defecto


def _init(args) -> int:
    claude = args.claude or shutil.which("claude")
    if not claude:
        print(
            "No encuentro `claude` en el PATH. Instalalo y logueate una vez "
            "(`claude`), o pasame la ruta con --claude.",
            file=sys.stderr,
        )
        return 2
    cfg = Config(url=args.url, token=args.token, claude_cmd=[claude], workdir=args.workdir)
    ruta = guardar(cfg, Path(args.config) if args.config else None)
    print(f"Config escrita en {ruta} (permisos 600).")
    return 0


def _run(args) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        cfg = cargar(Path(args.config) if args.config else None)
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 2
    try:
        asyncio.run(ejecutar(cfg, (Path(args.config).parent if args.config else None)))
    except ErrorFatal as e:
        print(f"Ragnar rechazo la conexion: {e}", file=sys.stderr)
        return SALIDA_AUTH
    except KeyboardInterrupt:
        pass
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="ragnar-bridge", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", help=f"ruta del config (default {ruta_por_defecto()})")
    sub = parser.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init", help="crea el archivo de configuracion")
    p_init.add_argument("--url", required=True, help="wss://.../api/v1/bridge/ws (la muestra la app)")
    p_init.add_argument("--token", required=True, help="ragbrg_... (la app lo muestra una sola vez)")
    p_init.add_argument("--claude", help="ruta de `claude` si no esta en el PATH")
    p_init.add_argument("--workdir", default="~", help="donde arranca cada turno (default ~)")
    p_init.set_defaults(fn=_init)

    p_run = sub.add_parser("run", help="conecta con Ragnar (es lo que corre el servicio)")
    p_run.set_defaults(fn=_run)

    args = parser.parse_args()
    if not args.cmd:
        args.fn = _run
    sys.exit(args.fn(args))
