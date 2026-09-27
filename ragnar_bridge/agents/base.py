"""Interfaz de un agente (CLI) que el bridge sabe manejar.

Ragnar espera SIEMPRE el mismo formato de eventos: las lineas de stream-json de
Claude Code (`stream_event`/`assistant`/`user`/`result`). Un agente cuyo CLI
emite otra cosa (Antigravity) trae un traductor que las convierte en el borde,
aca, para que el orquestador de Ragnar no tenga que saber que agentes existen.
"""

import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from ..config import Config
from ..protocolo import Turno


@dataclass
class Comando:
    argv: List[str]
    env: Dict[str, str]


def ventana(minutos: int) -> str:
    """Nombre corto de una ventana de cuota: 300 -> "5h", 10080 -> "semana"."""
    if minutos == 10080:
        return "semana"
    if minutos % 60 == 0:
        return f"{minutos // 60}h"
    return f"{minutos}min"


def bloque_de_cuota(grupo: Optional[str], ventana_: str, usado: float, resetea: Optional[datetime]) -> dict:
    """Un limite de la suscripcion en el formato que Ragnar espera de TODO
    agente: `usado` es un porcentaje entero (0-100) y `resetea` un instante ISO
    en UTC (o None si el CLI no lo dice)."""
    return {
        "grupo": grupo,
        "ventana": ventana_,
        "usado": max(0, min(100, round(usado))),
        "resetea": resetea.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if resetea else None,
    }


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

    def sesion_iniciada(self) -> Optional[bool]:
        """¿Tiene la sesion iniciada el usuario que corre el bridge? True/False,
        o None si no se pudo saber (el CLI no lo dice, timeout, sin red). Se usa
        solo para AVISAR en la app: nunca impide intentar un turno."""
        return None

    def cuota(self, version: str) -> Optional[dict]:
        """Cuota real de la suscripcion: `{"plan": str|None, "bloques": [...]}`
        (ver `bloque_de_cuota`), o None si el CLI no la expone o no se pudo
        leer. NUNCA gasta cuota ni lanza: es un dato de cortesia que viaja con
        el sondeo, y un fallo aca no debe tumbarlo."""
        return None

    def preparar(self, turno: Turno, username: str) -> Comando:
        raise NotImplementedError

    def traductor(self, turno: Turno) -> Traductor:
        return Traductor()
