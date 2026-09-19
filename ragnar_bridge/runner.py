"""Todo lo que toca el CLI de Claude en esta maquina: armar su comando, saber
si una sesion sigue viva, conceder permisos y escribir el MCP de tickets.

Es la parte que antes vivia dentro de claude_orchestrator.py en el servidor de
Ragnar (con CLAUDE_CONFIG_DIR por usuario); ahora corre aca, sobre TU sesion.
"""

import json
import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

from .config import Config

# El session_id llega de Ragnar y termina dentro de rutas (session-env/<id>,
# projects/.../<id>.jsonl): se exige forma de UUID para que un valor raro no
# pueda salirse de esas carpetas con "../".
_PATRON_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

# El CLI real sanea CUALQUIER caracter no alfanumerico del cwd a "-" para
# nombrar la carpeta de proyecto bajo <config_dir>/projects/ (verificado
# contra carpetas reales: un repo con "_" cae en una carpeta con "-").
_PATRON_NO_ALFANUMERICO = re.compile(r"[^a-zA-Z0-9]")

# Mismos patrones que permiso_es_catastrofico de claude_orchestrator.py: aunque
# Ragnar ya los filtra, el bridge es quien escribe en TU settings.json -- no
# confia en que el filtro de afuera siga ahi.
_PATRONES_PROHIBIDOS = (":(){ :|:& };:", "mkfs", "> /dev/sd")
_PATRON_RM_RAIZ = re.compile(r"rm\s+-[a-zA-Z-]*\s+/(?:\s|[\"')*]|$)")


class RunInvalido(Exception):
    """El `run` de Ragnar no tiene la forma esperada."""


def validar_run(run: dict) -> Tuple[str, str, str, str, Optional[str]]:
    """(session_id, prompt, prompt_fallback, system_append, conceder)."""
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
    return session_id, prompt, fallback, system_append, conceder or None


def permiso_es_catastrofico(tool: str) -> bool:
    chico = tool.strip().lower()
    if chico in ("bash(*)", "bash( * )", "*"):
        return True
    if _PATRON_RM_RAIZ.search(chico):
        return True
    return any(p in chico for p in _PATRONES_PROHIBIDOS)


def hay_sesion(cfg: Config, session_id: str) -> bool:
    """¿Sigue el CLI guardando esta conversacion? Cada sesion es un .jsonl bajo
    <config_dir>/projects/<cwd saneado>/. `--resume` de una sesion inexistente
    responde «No conversation found» y sale con codigo 0 (la tarea quedaba
    «completada» con ese texto), asi que se comprueba ANTES."""
    carpeta = _PATRON_NO_ALFANUMERICO.sub("-", cfg.workdir_abs)
    return (Path(cfg.config_dir_abs) / "projects" / carpeta / f"{session_id}.jsonl").is_file()


def limpiar_lock_sesion(cfg: Config, session_id: str) -> None:
    """En modo --print el CLI nunca limpia <config_dir>/session-env/<id>/ (eso
    pasa en una salida interactiva): si queda de una invocacion anterior, la
    siguiente --session-id/--resume del MISMO id responde «Session ID ... is
    already in use» sin que haya proceso vivo. Se llama antes de cada
    invocacion propia."""
    shutil.rmtree(Path(cfg.config_dir_abs) / "session-env" / session_id, ignore_errors=True)


def conceder_permiso(cfg: Config, tool: str) -> bool:
    """Suma `tool` a permissions.allow de TU settings.json (el humano ya lo
    aprobo en la app de Ragnar). Escritura atomica: un JSON a medio escribir
    tumbaria tambien tus sesiones interactivas. Devuelve False si no se
    escribio (patron bloqueado o settings ilegible)."""
    if permiso_es_catastrofico(tool):
        return False
    ruta = Path(cfg.config_dir_abs) / "settings.json"
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(datos, dict):
        return False
    permisos = datos.setdefault("permissions", {}).setdefault("allow", [])
    if tool in permisos:
        return True
    permisos.append(tool)
    tmp = ruta.with_name(ruta.name + f".tmp-{os.getpid()}")
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, ruta)
    except OSError:
        return False
    return True


def url_mcp_tickets(ws_url: str) -> Optional[str]:
    """https://<panel>/api/v1/mcp a partir de wss://<panel>/api/v1/bridge/ws."""
    partes = urlsplit(ws_url)
    sufijo = "/bridge/ws"
    if not partes.path.endswith(sufijo):
        return None
    esquema = "https" if partes.scheme == "wss" else "http"
    ruta = partes.path[: -len(sufijo)] + "/mcp"
    return urlunsplit((esquema, partes.netloc, ruta, "", ""))


def escribir_mcp_config(cfg: Config, estado_dir: Path, username: str) -> Optional[str]:
    """MCP de tickets de Ragnar autenticado como TU usuario (con tu propio
    ragagt_), o None si no configuraste `tickets_token`. Se regenera en cada
    turno: barato, y evita servir un token que ya cambiaste o revocaste."""
    if not cfg.tickets_token:
        return None
    url = url_mcp_tickets(cfg.url)
    if not url:
        return None
    estado_dir.mkdir(parents=True, exist_ok=True)
    ruta = estado_dir / "mcp-config.json"
    contenido = {
        "mcpServers": {
            "tickets": {
                "type": "http",
                "url": url,
                "headers": {
                    "Authorization": f"Bearer {cfg.tickets_token}",
                    "X-Agent-Name": username,
                },
            }
        }
    }
    tmp = ruta.with_name(ruta.name + f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(contenido, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, ruta)
    return str(ruta)


def construir_comando(
    cfg: Config,
    session_id: str,
    prompt: str,
    prompt_fallback: str,
    system_append: str,
    mcp_config: Optional[str],
) -> Tuple[List[str], Dict[str, str]]:
    """Comando y entorno de UN turno. Si la sesion sigue viva se retoma con
    `prompt`; si no, se abre con `prompt_fallback`, que ya trae el hilo
    anterior rehecho por prompt (ver prompt_con_contexto en Ragnar)."""
    reanudar = hay_sesion(cfg, session_id)
    texto = prompt if reanudar else prompt_fallback
    # Un prompt que empieza con "-" el CLI lo leeria como un flag.
    if texto.startswith("-"):
        texto = " " + texto

    cmd = [
        *cfg.claude_cmd,
        "--print",
        "--output-format=stream-json",
        "--include-partial-messages",
        "--verbose",
    ]
    if system_append:
        cmd += ["--append-system-prompt", system_append]
    if mcp_config:
        cmd += ["--mcp-config", mcp_config]
    if cfg.add_dirs:
        cmd += ["--add-dir", *[os.path.abspath(os.path.expanduser(d)) for d in cfg.add_dirs]]
    cmd += ["--resume" if reanudar else "--session-id", session_id, texto]

    env = os.environ.copy()
    # Solo se fija CLAUDE_CONFIG_DIR si la moviste de sitio: con la variable
    # puesta el CLI guarda su estado (.claude.json) DENTRO de esa carpeta, no
    # junto a ella en ~/, y eso rompe tu sesion ya iniciada.
    por_defecto = os.path.abspath(os.path.expanduser("~/.claude"))
    if cfg.config_dir_abs != por_defecto:
        env["CLAUDE_CONFIG_DIR"] = cfg.config_dir_abs
    return cmd, env
