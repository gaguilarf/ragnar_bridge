from pathlib import Path
from typing import Dict, List

from ..config import Config
from .base import Adaptador


def _crear(nombre: str, cfg: Config, estado_dir: Path) -> Adaptador:
    if nombre == "claude":
        from .claude import ClaudeAdaptador

        return ClaudeAdaptador(cfg, estado_dir)
    if nombre == "agy":
        from .agy import AgyAdaptador

        return AgyAdaptador(cfg, estado_dir)
    raise ValueError(f"Agente desconocido: {nombre!r}")


def crear_adaptadores(cfg: Config, estado_dir: Path) -> Dict[str, Adaptador]:
    """Un adaptador por cada agente que este bridge intenta manejar (esten o no
    instalados: eso lo dice `sondear`)."""
    return {nombre: _crear(nombre, cfg, estado_dir) for nombre in cfg.agentes_pedidos()}


def crear_adaptador(cfg: Config, estado_dir: Path) -> Adaptador:
    """Compatibilidad: el primer agente pedido."""
    return next(iter(crear_adaptadores(cfg, estado_dir).values()))


def sondear(adaptadores: Dict[str, Adaptador]) -> List[dict]:
    """Los agentes que de verdad estan instalados, con su version y si tienen
    sesion iniciada (True/False/None = no se sabe). Bloquea (lanza los CLIs):
    desde codigo async, con asyncio.to_thread."""
    encontrados = []
    for nombre, adaptador in adaptadores.items():
        if not adaptador.encontrado():
            continue
        encontrados.append(
            {
                "name": nombre,
                "cli_version": adaptador.version(),
                "login": adaptador.sesion_iniciada(),
            }
        )
    return encontrados
