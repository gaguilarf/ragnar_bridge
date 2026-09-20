import argparse
import asyncio
import logging
import os
import shutil
import sys
from pathlib import Path

from . import __version__
from .agents import crear_adaptador
from .bridge import SALIDA_AUTH, ErrorFatal, ejecutar, probar_conexion
from .config import AGENTES, Config, ConfigError, cargar, guardar, ruta_por_defecto


def _init(args) -> int:
    binario = args.cli or shutil.which(args.agent)
    if not binario:
        print(
            f"No encuentro `{args.agent}` en el PATH. Instalalo y logueate una vez "
            f"(corre `{args.agent}`), o pasame la ruta con --cli.",
            file=sys.stderr,
        )
        return 2
    cfg = Config(url=args.url, token=args.token, agent=args.agent, workdir=args.workdir)
    if args.agent == "claude":
        cfg.claude_cmd = [binario]
    else:
        cfg.agy_cmd = [binario]
        if args.model:
            cfg.agy_model = args.model
    ruta = guardar(cfg, Path(args.config) if args.config else None)
    print(f"Config escrita en {ruta} (permisos 600), agente: {args.agent}.")
    return 0


def _doctor(args) -> int:
    """Verifica cada eslabon SIN correr ningun turno (no gasta cuota)."""
    ok = True

    def paso(bien: bool, texto: str) -> None:
        nonlocal ok
        ok = ok and bien
        print(f"  [{'ok' if bien else 'FALLA'}] {texto}")

    ruta = Path(args.config) if args.config else ruta_por_defecto()
    print(f"ragnar-bridge {__version__}")
    try:
        cfg = cargar(ruta)
    except ConfigError as e:
        paso(False, str(e))
        return 1
    paso(True, f"config {ruta} (agente: {cfg.agent})")

    adaptador = crear_adaptador(cfg, ruta.parent)
    if adaptador.encontrado():
        paso(True, f"CLI {' '.join(adaptador.cmd)} -> version {adaptador.version()}")
    else:
        paso(False, f"no encuentro `{adaptador.cmd[0]}`: instalalo, o fija la ruta en el config")
    paso(os.path.isdir(cfg.workdir_abs), f"carpeta de trabajo {cfg.workdir_abs}")

    try:
        nombre = asyncio.run(probar_conexion(cfg))
        paso(True, f"Ragnar acepto el token (servidor {nombre!r})")
    except ErrorFatal as e:
        paso(False, f"Ragnar rechazo la conexion: {e}")
    except Exception as e:  # red, DNS, TLS...
        paso(False, f"no pude conectar con {cfg.url}: {type(e).__name__}: {e}")

    print("Todo en orden." if ok else "Hay pasos con FALLA: corregilos y volve a correr `ragnar-bridge doctor`.")
    return 0 if ok else 1


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
    p_init.add_argument("--agent", choices=AGENTES, default="claude", help="que CLI maneja este bridge")
    p_init.add_argument("--cli", help="ruta del CLI si no esta en el PATH")
    p_init.add_argument("--model", help="(agy) modelo, ver `agy models`")
    p_init.add_argument("--workdir", default="~", help="donde arranca cada turno (default ~)")
    p_init.set_defaults(fn=_init)

    p_doc = sub.add_parser("doctor", help="verifica config, CLI y conexion con Ragnar (sin gastar cuota)")
    p_doc.set_defaults(fn=_doctor)

    p_run = sub.add_parser("run", help="conecta con Ragnar (es lo que corre el servicio)")
    p_run.set_defaults(fn=_run)

    args = parser.parse_args()
    if not args.cmd:
        args.fn = _run
    sys.exit(args.fn(args))
