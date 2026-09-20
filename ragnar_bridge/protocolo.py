"""Forma de un `run` de Ragnar y reglas que valen para CUALQUIER agente."""

import re
from dataclasses import dataclass
from typing import Optional

# El session_id llega de Ragnar y termina dentro de rutas y de un archivo de
# estado: se exige forma de UUID para que un valor raro no pueda salirse de
# las carpetas del CLI con "../".
_PATRON_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# Mismos patrones que permiso_es_catastrofico de claude_orchestrator.py: aunque
# Ragnar ya los filtra, el bridge es quien escribe en TU configuracion -- no
# confia en que el filtro de afuera siga ahi.
_PATRONES_PROHIBIDOS = (":(){ :|:& };:", "mkfs", "> /dev/sd")
_PATRON_RM_RAIZ = re.compile(r"rm\s+-[a-zA-Z-]*\s+/(?:\s|[\"')*]|$)")


class RunInvalido(Exception):
    """El `run` de Ragnar no tiene la forma esperada."""


@dataclass(frozen=True)
class Turno:
    """Un `run` ya validado."""

    session_id: str
    prompt: str
    # Prompt que ya trae el hilo anterior rehecho: se usa cuando la sesion del
    # CLI no existe (primer turno, o se perdio).
    prompt_fallback: str
    # Instrucciones del protocolo pregunta/permiso de Ragnar.
    system_append: str
    # Permiso que el humano ya aprobo en la app (o None).
    conceder: Optional[str]


def validar_run(run: dict) -> Turno:
    session_id = run.get("session_id")
    if not isinstance(session_id, str) or not _PATRON_UUID.match(session_id):
        raise RunInvalido("session_id invalido")
    prompt = run.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise RunInvalido("prompt vacio")
    fallback = run.get("prompt_fallback")
    if not isinstance(fallback, str) or not fallback.strip():
        fallback = prompt
    system_append = run.get("system_append")
    if not isinstance(system_append, str):
        system_append = ""
    conceder = run.get("conceder")
    if conceder is not None and not isinstance(conceder, str):
        raise RunInvalido("conceder invalido")
    return Turno(session_id, prompt, fallback, system_append, conceder or None)


def permiso_es_catastrofico(tool: str) -> bool:
    chico = tool.strip().lower()
    if chico in ("bash(*)", "bash( * )", "*"):
        return True
    if _PATRON_RM_RAIZ.search(chico):
        return True
    return any(p in chico for p in _PATRONES_PROHIBIDOS)
