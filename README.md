# ragnar-bridge

Corre el CLI de Claude en **tu propio servidor** y le reenvía a Ragnar lo que
emite, por una conexión WebSocket **saliente**. Tus credenciales de Claude no
salen de tu máquina y no hace falta abrir ningún puerto.

```
tu VPS                                        Ragnar
┌──────────────────────┐   wss (saliente)   ┌──────────────────┐
│ claude (tu sesión)   │ ─────────────────► │ /api/v1/bridge/ws│
│   ▲                  │ ◄───────────────── │  chat de la app  │
│   └─ ragnar-bridge   │  run / event / done└──────────────────┘
└──────────────────────┘
```

## Instalar

1. En la app de Ragnar: **Conectar mi servidor** → poné un nombre → te muestra
   una URL y un token (`ragbrg_...`). El token se muestra **una sola vez**.
2. En tu VPS, con `claude` ya instalado y logueado (corré `claude` una vez):

```sh
curl -fsSL https://raw.githubusercontent.com/gaguilarf/ragnar_bridge/main/install.sh \
  | bash -s -- --url wss://panel.ragnargroup.app/api/v1/bridge/ws --token ragbrg_...
```

Crea un entorno en `~/.local/share/ragnar-bridge`, escribe
`~/.config/ragnar-bridge/config.json` (permisos 600) y deja un servicio de
systemd de usuario. Sin systemd: `ragnar-bridge run`.

## Configuración

`~/.config/ragnar-bridge/config.json` (o `RAGNAR_BRIDGE_CONFIG`):

| campo | default | para qué |
|---|---|---|
| `url`, `token` | — | los que muestra la app |
| `claude_cmd` | `["claude"]` | comando del CLI (lista, por si es un wrapper) |
| `workdir` | `~` | dónde arranca cada turno |
| `add_dirs` | `[]` | directorios extra accesibles (`--add-dir`) |
| `config_dir` | `~/.claude` | carpeta de config/credenciales del CLI |
| `tickets_token` | — | tu `ragagt_...`, si querés las tools de tickets de Ragnar |
| `max_turnos` | `4` | conversaciones simultáneas |

## Qué hace y qué no

- Cada turno lanza `claude --print --output-format=stream-json` con **tu**
  sesión y reenvía sus líneas sin traducirlas.
- Los permisos que aprobás en la app se escriben en **tu**
  `~/.claude/settings.json` (nunca patrones tipo `Bash(*)` ni `rm -rf /`).
- Si se corta la conexión con Ragnar, el bridge **mata** los turnos en curso:
  nadie estaría viendo lo que el agente hace en tu servidor. Reconecta solo,
  con backoff.
- El agente corre con los permisos del usuario que arrancó el bridge: usá un
  usuario sin privilegios, no root.
- Ragnar ve el contenido de tus conversaciones (prompts y resultados de
  herramientas, estos últimos recortados) — lo que no ve es tu sesión de Claude.

## Desarrollo

```sh
pip install -e '.[dev]'
pytest
```

El protocolo está documentado en `services/bridge_hub.py` de `ragnar_group_back`
(fuente de verdad); `PROTOCOLO` en `ragnar_bridge/__init__.py` tiene que
coincidir.

## Pendiente

- Cuota real de la suscripción (`/usage` por pty) como comando del protocolo.
- Adaptador para `agy` (Antigravity CLI): hoy solo `claude`.
