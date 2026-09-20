"""Interfaz de un agente (CLI) que el bridge sabe manejar.

Ragnar espera SIEMPRE el mismo formato de eventos: las lineas de stream-json de
Claude Code (`stream_event`/`assistant`/`user`/`result`). Un agente cuyo CLI
emite otra cosa (Antigravity) trae un traductor que las convierte en el borde,
aca, para que el orquestador de Ragnar no tenga que saber que agentes existen.
"""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from ..config import Config
from ..protocolo import Turno


@dataclass
class Comando:
    argv: List[str]
    env: Dict[str, str]


class Traductor:
    """Estado de UN turno: convierte lo que emite el CLI en eventos para
    Ragnar. Por defecto no traduce nada (el CLI ya habla el formato de Ragnar)."""

    def evento(self, linea: dict) -> List[dict]:
        return [linea]

    def fin(self, codigo: Optional[int], stderr: str) -> List[dict]:
        """Se llama una vez, cuando el proceso ya termino. Devuelve eventos
        finales que faltaban (y es el lugar para persistir estado del turno)."""
        return []


class Adaptador:
    nombre = ""

    def __init__(self, cfg: Config, estado_dir: Path):
        self.cfg = cfg
        self.estado_dir = estado_dir

    @property
    def cmd(self) -> List[str]:
        raise NotImplementedError

    def version(self) -> str:
        try:
            salida = subprocess.run(
                [*self.cmd, "--version"], capture_output=True, text=True, timeout=20
            )
            return (salida.stdout or salida.stderr).strip()[:80] or "desconocida"
        except (OSError, subprocess.SubprocessError):
            return "no encontrado"

    def encontrado(self) -> bool:
        return shutil.which(self.cmd[0]) is not None

    def preparar(self, turno: Turno, username: str) -> Comando:
        raise NotImplementedError

    def traductor(self, turno: Turno) -> Traductor:
        return Traductor()
