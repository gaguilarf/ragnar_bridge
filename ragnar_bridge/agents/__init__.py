from pathlib import Path

from ..config import Config
from .base import Adaptador


def crear_adaptador(cfg: Config, estado_dir: Path) -> Adaptador:
    """El adaptador del agente configurado (`cfg.agent`)."""
    if cfg.agent == "claude":
        from .claude import ClaudeAdaptador

        return ClaudeAdaptador(cfg, estado_dir)
    if cfg.agent == "agy":
        from .agy import AgyAdaptador

        return AgyAdaptador(cfg, estado_dir)
    raise ValueError(f"Agente desconocido: {cfg.agent!r}")
