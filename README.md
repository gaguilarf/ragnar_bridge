# ragnar-bridge

Corre **Claude Code** o **Antigravity (`agy`)** en **tu propio servidor** y le
reenvía a Ragnar lo que emite, por una conexión WebSocket **saliente**. Tus
credenciales del CLI no salen de tu máquina y no hace falta abrir ningún puerto.

```
tu VPS                                          Ragnar
┌────────────────────────────┐  wss (saliente)  ┌───────────────────┐
│ claude  ó  agy (tu sesión) │ ───────────────► │ /api/v1/bridge/ws │
│    ▲                       │ ◄─────────────── │   chat de la app  │
│    └─ ragnar-bridge        │  run / event     └───────────────────┘
└────────────────────────────┘
```

Un bridge maneja **un** agente. Si querés los dos, instalás dos bridges (paso 7).

## Qué necesitás

- Un servidor Linux con `python3` (≥ 3.9, con el módulo `venv`) y salida a
  internet por HTTPS. Mejor con un **usuario sin privilegios** (no root): el
  agente corre con los permisos de quien arranca el bridge.
- **Una** de las dos cuentas ya funcionando en ese servidor:
  - Claude Code con una cuenta de Claude, o
  - Antigravity CLI con una cuenta de Google.

## Paso 1 — Elegí el agente

| | Claude Code | Antigravity (`agy`) |
|---|---|---|
| Comando | `claude` | `agy` |
| Sesión de la conversación | `--session-id` / `--resume` (la maneja el CLI) | el bridge recuerda qué conversación de agy es cuál (`agy-estado.json`) |
| Permisos de herramientas | Ragnar te muestra la tarjeta **Autorizar**; al aprobar, el bridge suma **esa** herramienta a tu `~/.claude/settings.json` | agy **deniega** solo lo que pide permiso (en modo headless no puede preguntar). Ragnar te muestra la misma tarjeta; al aprobar, **esa conversación** corre con las herramientas aprobadas |
| Herramientas de tickets de Ragnar (MCP) | sí (`tickets_token`) | todavía no |
| Cuota real de la suscripción | todavía no | todavía no |
| Probado con | Claude Code 2.1.170 | agy 1.1.27 y 1.2.7 |

## Paso 2 — Prepará el CLI en tu VPS

Hacé **uno** de los dos y comprobá que responde **antes** de instalar el bridge.

### A) Claude Code

```sh
curl -fsSL https://claude.ai/install.sh | bash     # o: npm install -g @anthropic-ai/claude-code
claude                                              # primer arranque: te da un link, lo abrís en tu
                                                    # navegador y pegás el código de vuelta
claude --version
claude -p "respondé solo OK"                        # debe contestar OK
```

### B) Antigravity CLI

```sh
curl -fsSL https://antigravity.google/cli/install.sh | bash
agy                                                 # primer arranque: login por dispositivo, abrís el
                                                    # link en tu navegador y pegás el código de vuelta
agy --version
agy models                                          # lista los modelos disponibles
agy "-p=respondé solo OK"                           # debe contestar OK
```

Si después de instalar el comando no se encuentra, abrí una terminal nueva (el
PATH se recarga al iniciar sesión).

## Paso 3 — Registrá el servidor en la app

En la app de Ragnar: **Agents → Conectá tu servidor** → poné un nombre → te
muestra el comando de instalación con tu URL y tu token (`ragbrg_...`).
**El token se muestra una sola vez**: si lo perdés, revocás ese servidor y
generás otro.

### ¿Personal o para todo el grupo?

En **Quién lo usa** elegís:

- **Todo el grupo «X»** (recomendado si varias personas usan el mismo VPS):
  se instala **un solo bridge** y todos los miembros del grupo chatean a través
  de él. Un solo CLI, una sola versión, una sola cuenta: nadie se queda con su
  `claude`/`agy` desactualizado por su cuenta. Los miembros no instalan nada;
  al abrir Agents ya lo ven conectado.
- **Solo yo (personal)**: nadie más lo ve ni lo puede usar.

Alguien de **otro grupo** no puede usar tu bridge compartido: tiene que
instalar el suyo.

Tené en cuenta en un bridge compartido:

- Todos los miembros ejecutan en el **mismo servidor y con la misma cuenta**
  del CLI (la cuota es una sola). Los archivos y el `settings.json` son los
  mismos para todos: un permiso que uno autoriza queda autorizado para el resto.
- Cada conversación es de quien la creó (los demás no la ven), pero comparten
  el disco del VPS.
- Si ponés `tickets_token`, las acciones sobre tickets salen a nombre de **esa**
  persona para todos. En un bridge compartido conviene dejarlo vacío.
- Lo puede revocar quien lo creó o cualquier miembro del grupo (así no queda
  huérfano si su creador se va).
- Si un miembro tiene su propio bridge **y** hay uno compartido, sus
  conversaciones nuevas usan el propio; una conversación que ya vive en uno
  sigue en ese.

## Paso 4 — Instalá el bridge

Pegá en tu VPS el comando de la app, agregando el agente que elegiste:

```sh
# Claude Code
curl -fsSL https://raw.githubusercontent.com/gaguilarf/ragnar_bridge/main/install.sh \
  | bash -s -- --agent claude --url wss://panel.ragnargroup.app/api/v1/bridge/ws --token ragbrg_...

# Antigravity (opcional: --model para fijar el modelo)
curl -fsSL https://raw.githubusercontent.com/gaguilarf/ragnar_bridge/main/install.sh \
  | bash -s -- --agent agy --model gemini-3.7-flash-high --url wss://panel.ragnargroup.app/api/v1/bridge/ws --token ragbrg_...
```

Opciones: `--workdir DIR` (dónde arranca cada turno, por defecto tu home),
`--name N` (para tener dos bridges, paso 7). El script:

1. crea un entorno en `~/.local/share/ragnar-bridge`;
2. escribe `~/.config/ragnar-bridge/config.json` (permisos 600);
3. corre `ragnar-bridge doctor` y **se detiene si algo falla**;
4. deja un servicio de systemd de usuario y activa *linger* para que siga
   corriendo al cerrar tu sesión SSH.

## Paso 5 — Verificá

```sh
~/.local/share/ragnar-bridge/venv/bin/ragnar-bridge doctor
systemctl --user status ragnar-bridge
journalctl --user -u ragnar-bridge -f
```

`doctor` no corre ningún turno (no gasta cuota); comprueba, en orden: el config,
que el CLI exista y su versión, la carpeta de trabajo, y que Ragnar acepte tu
token. En la app, **Mis servidores** debe mostrar el tuyo con un punto verde.

## Paso 6 — Probalo

En el chat de Agents escribí `respondé solo OK`. Después pedile algo que
necesite una herramienta, por ejemplo `listá los archivos de la carpeta actual`:
vas a ver la tarjeta **Autorizar** (paso siguiente).

### Cómo funcionan los permisos

- **Claude Code**: la tarjeta dice qué herramienta pide (ej. `Bash(docker *)`).
  Al aprobar, el bridge la agrega a `permissions.allow` de tu
  `~/.claude/settings.json` y retoma el turno. Nunca acepta patrones tipo
  `Bash(*)` ni `rm -rf /`.
- **Antigravity**: agy en modo headless **no puede preguntar** y `permissions.allow`
  de su `settings.json` se ignora ahí (issue #548 de antigravity-cli). La única
  forma de destrabarlo es aprobar *todas* las herramientas, así que el bridge
  no lo hace de entrada: deja que agy deniegue, te muestra la tarjeta
  `agy:permisos` con lo que intentó hacer, y **solo si aprobás** esa
  conversación pasa a correr con las herramientas aprobadas (el permiso es de
  esa conversación, no de las demás). Se controla con `agy_permisos`:

| `agy_permisos` | Qué pasa |
|---|---|
| `preguntar` (default) | Ragnar te pregunta; si aprobás, esa conversación queda aprobada |
| `denegar` | Nunca se concede: el agente solo lee y conversa |
| `auto` | Todo aprobado siempre (`--dangerously-skip-permissions`). **Solo en un servidor desechable** |

## Configuración

`~/.config/ragnar-bridge/config.json` (o donde diga `RAGNAR_BRIDGE_CONFIG`):

| campo | default | para qué |
|---|---|---|
| `url`, `token` | — | los que muestra la app |
| `agent` | `claude` | `claude` o `agy` |
| `claude_cmd` / `agy_cmd` | `["claude"]` / `["agy"]` | comando del CLI (lista, por si es un wrapper) |
| `workdir` | `~` | dónde arranca cada turno |
| `add_dirs` | `[]` | directorios extra accesibles (`--add-dir`) |
| `config_dir` | `~/.claude` | (claude) carpeta de config del CLI |
| `tickets_token` | — | (claude) tu `ragagt_...`, para las tools de tickets de Ragnar |
| `agy_model` | — | (agy) modelo; vacío = el default de agy. Ver `agy models` |
| `agy_timeout` | `30m` | (agy) tope de un turno (`--print-timeout`) |
| `agy_permisos` | `preguntar` | (agy) ver arriba |
| `agy_dir` | `~/.gemini/antigravity-cli` | (agy) dónde agy guarda sus conversaciones |
| `max_turnos` | `4` | conversaciones simultáneas |

Después de editarlo: `systemctl --user restart ragnar-bridge`.

## Paso 7 — (opcional) Los dos agentes a la vez

Cada bridge maneja un agente y tiene su propio token: creá **otro** servidor en
la app y corré el instalador de nuevo con `--name`:

```sh
... | bash -s -- --agent agy --name agy --url ... --token <token-del-segundo-servidor>
# queda como servicio "ragnar-bridge-agy" y config "config-agy.json"
```

## Qué hace y qué no hace

- Cada turno lanza el CLI en modo no interactivo con **tu** sesión y reenvía sus
  eventos. Para Antigravity el bridge traduce sus eventos al formato que Ragnar
  entiende (texto, herramientas y resultados, uso de tokens).
- Si se corta la conexión con Ragnar, el bridge **mata** los turnos en curso:
  nadie estaría viendo lo que el agente hace en tu servidor. Reconecta solo, con
  backoff.
- Ragnar ve el contenido de tus conversaciones (prompts y resultados de
  herramientas, estos últimos recortados). Lo que **no** ve es tu sesión de
  Claude o de Google.
- Un token filtrado equivale a ejecutar comandos en tu servidor con los permisos
  del usuario del bridge: revocalo desde **Mis servidores** (corta el socket en
  el acto) y usá un usuario sin privilegios.

## Solución de problemas

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| La app dice *«Tu servidor no está conectado»* | el servicio está caído o no sale a internet | `systemctl --user status ragnar-bridge`; `ragnar-bridge doctor` |
| `doctor`: *«Credencial inválida o revocada»* | token mal copiado o servidor revocado | generá otro servidor en la app y reinstalá |
| `doctor`: *«Protocolo … no soportado»* | Ragnar es más nuevo que tu bridge | actualizá (más abajo) |
| `doctor`: *«no encuentro `claude`/`agy`»* | el servicio no ve tu PATH | reinstalá desde una terminal donde el comando funcione, o poné la ruta absoluta en `claude_cmd`/`agy_cmd` |
| El servicio se apaga al cerrar SSH | falta *linger* | como root: `loginctl enable-linger <usuario>` |
| El servicio no reintenta y sale con 78 | Ragnar rechazó el token | es a propósito: generá un token nuevo |
| (agy) el agente dice que no pudo ejecutar un comando | agy denegó la herramienta | aprobá la tarjeta en la app, o `agy_permisos` |
| (agy) un turno largo se corta a los 30 min | `agy_timeout` | subilo en el config (`"2h"`) |
| (claude) *«No conversation found»* / *«Session ID already in use»* | el bridge ya lo evita (comprueba la sesión y limpia el lock) | si aparece igual, abrí un issue con el log |

## Actualizar

```sh
~/.local/share/ragnar-bridge/venv/bin/pip install --upgrade git+https://github.com/gaguilarf/ragnar_bridge
systemctl --user restart ragnar-bridge
```

## Desinstalar

```sh
systemctl --user disable --now ragnar-bridge
rm -rf ~/.local/share/ragnar-bridge ~/.config/ragnar-bridge ~/.config/systemd/user/ragnar-bridge*.service
```

Y revocá el servidor desde **Mis servidores** en la app.

## macOS / Windows

El instalador es solo Linux + systemd. En otros sistemas se instala a mano (el
bridge en sí corre en Windows, probado en Windows 11):

```sh
python -m venv venv && venv/bin/pip install git+https://github.com/gaguilarf/ragnar_bridge   # Windows: venv\Scripts\pip
ragnar-bridge init --agent claude --url wss://... --token ragbrg_...                          # o --agent agy
ragnar-bridge doctor
ragnar-bridge run            # dejalo corriendo (launchd en macOS, Tareas programadas o NSSM en Windows)
```

## Desarrollo

```sh
pip install -e '.[dev]'
pytest
```

Las pruebas usan un Ragnar de mentira (`tests/helpers.py`) y dobles del CLI
(`tests/fake_claude.py`, `tests/fake_agy.py`); el de agy emite los eventos reales
capturados de agy 1.1.27.

El protocolo está documentado en `services/bridge_hub.py` de `ragnar_group_back`
(fuente de verdad); `PROTOCOLO` en `ragnar_bridge/__init__.py` tiene que
coincidir. Para sumar otro agente: una clase en `ragnar_bridge/agents/` que
arme el comando y traduzca sus eventos al formato de Claude Code (ver
`agents/agy.py`), y registrarla en `agents/__init__.py`.

## Pendiente

- Cuota real de la suscripción como comando del protocolo (hoy `POST /claude/quota`
  responde 501).
- Tools de tickets de Ragnar (MCP) para Antigravity.
