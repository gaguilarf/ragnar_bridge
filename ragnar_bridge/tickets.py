"""Que token y que URL usa el agente de un turno para hablar con los tickets de
Ragnar. Lo comparten Claude (MCP HTTP directo) y agy (por `mcp_proxy`)."""

from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from .config import Config
from .protocolo import Turno


def url_mcp_tickets(ws_url: str) -> Optional[str]:
    """https://<panel>/api/v1/mcp/ a partir de wss://<panel>/api/v1/bridge/ws.

    CON la barra final: el backend monta el MCP en /api/v1/mcp/ y, detras del
    proxy de produccion, `POST /api/v1/mcp` (sin barra) responde 405 en vez de
    redirigir -- Claude Code no llegaba a conectar y el agente se quedaba sin
    tools de tickets."""
    partes = urlsplit(ws_url)
    sufijo = "/bridge/ws"
    if not partes.path.endswith(sufijo):
        return None
    esquema = "https" if partes.scheme == "wss" else "http"
    ruta = partes.path[: -len(sufijo)] + "/mcp/"
    return urlunsplit((esquema, partes.netloc, ruta, "", ""))


def token_de_tickets(cfg: Config, turno: Turno) -> Optional[str]:
    """El token con el que el agente de ESTE turno llama a Ragnar. Si Ragnar
    manda el suyo (efimero, del usuario que escribio) es el unico que vale, aun
    vacio: en un bridge compartido el `tickets_token` de la config es de UNA
    persona, y usarlo de reemplazo haria actuar a todo el grupo como ella. Solo
    un Ragnar viejo, que no manda el campo, cae al de la config."""
    if turno.token_de_turno:
        return turno.tickets_token
    return cfg.tickets_token
