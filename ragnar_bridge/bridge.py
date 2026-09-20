"""Conexion con Ragnar y ejecucion de turnos. Protocolo: ver el docstring de
services/bridge_hub.py en ragnar_group_back (es la fuente de verdad)."""

import asyncio
import json
import logging
import random
from pathlib import Path
from typing import Dict, Optional

from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

from . import PROTOCOLO, __version__
from .agents import crear_adaptador
from .config import Config, ruta_por_defecto
from .protocolo import RunInvalido, validar_run

log = logging.getLogger("ragnar_bridge")

# Salida distinta a 1 para que systemd (RestartPreventExitStatus=78) no
# reintente para siempre con un token que Ragnar ya rechazo.
SALIDA_AUTH = 78

# El limite de frame de Ragnar (uvicorn) es 16 MiB; un `event` con un
# tool_result grande viaja como UN frame.
MAX_FRAME = 32 * 1024 * 1024


class ErrorFatal(Exception):
    """Ragnar rechazo la conexion de forma que reintentar no arregla nada
    (token revocado/invalido, protocolo incompatible)."""


class Bridge:
    def __init__(self, cfg: Config, estado_dir: Optional[Path] = None):
        self.cfg = cfg
        self.estado_dir = estado_dir or ruta_por_defecto().parent
        self.adaptador = crear_adaptador(cfg, self.estado_dir)
        self._ws = None
        self._envio = asyncio.Lock()
        self._procesos: Dict[str, asyncio.subprocess.Process] = {}
        self._tareas: Dict[str, asyncio.Task] = {}
        self.username = "bridge"

    # ---- envio

    async def enviar(self, mensaje: dict) -> None:
        # Varias tareas (una por turno) escriben al mismo socket.
        async with self._envio:
            await self._ws.send(json.dumps(mensaje, ensure_ascii=False))

    # ---- una conexion completa (auth -> welcome -> bucle de frames)

    async def sesion(self, ws) -> None:
        self._ws = ws
        await ws.send(
            json.dumps(
                {
                    "type": "auth",
                    "token": self.cfg.token,
                    "protocol": PROTOCOLO,
                    "version": __version__,
                    "agent": self.adaptador.nombre,
                    "cli_version": self.adaptador.version(),
                }
            )
        )
        bienvenida = json.loads(await asyncio.wait_for(ws.recv(), 15))
        if bienvenida.get("type") == "error":
            if bienvenida.get("code") in ("auth", "protocol"):
                raise ErrorFatal(bienvenida.get("message") or bienvenida.get("code"))
            raise WebSocketException(bienvenida.get("message") or "error de Ragnar")
        if bienvenida.get("type") != "welcome":
            raise WebSocketException(f"Respuesta inesperada de Ragnar: {bienvenida.get('type')!r}")
        self.username = str(bienvenida.get("username") or "bridge")
        log.info(
            "Conectado a Ragnar como %s (servidor %r).", self.username, bienvenida.get("nombre")
        )

        try:
            async for crudo in ws:
                try:
                    mensaje = json.loads(crudo)
                except json.JSONDecodeError:
                    continue
                if isinstance(mensaje, dict):
                    await self._atender(mensaje)
        finally:
            # Sin Ragnar del otro lado nadie ve lo que el agente hace en tu
            # servidor: se cortan los turnos en curso (Ragnar los da por
            # fallidos al ver el socket caer).
            await self._cortar_todo()
            self._ws = None

    async def _atender(self, mensaje: dict) -> None:
        tipo = mensaje.get("type")
        task_id = str(mensaje.get("task_id") or "")
        if tipo == "run":
            if len(self._tareas) >= self.cfg.max_turnos:
                await self.enviar({"type": "error", "task_id": task_id, "message": "El servidor ya tiene el maximo de turnos en curso."})
                return
            if task_id in self._tareas:
                await self.enviar({"type": "error", "task_id": task_id, "message": "Esa conversacion ya tiene un turno en curso."})
                return
            tarea = asyncio.create_task(self._turno(task_id, mensaje))
            self._tareas[task_id] = tarea
            tarea.add_done_callback(lambda _t, tid=task_id: self._tareas.pop(tid, None))
        elif tipo == "cancel":
            await self._matar(task_id)
        elif tipo == "error":
            log.warning("Ragnar: %s", mensaje.get("message"))

    # ---- un turno

    async def _turno(self, task_id: str, run: dict) -> None:
        try:
            turno = validar_run(run)
        except RunInvalido as e:
            await self.enviar({"type": "error", "task_id": task_id, "message": f"run invalido: {e}"})
            return

        try:
            comando = self.adaptador.preparar(turno, self.username)
        except OSError as e:
            await self.enviar(
                {"type": "error", "task_id": task_id, "message": f"No se pudo preparar el turno: {e}"}
            )
            return
        traductor = self.adaptador.traductor(turno)

        try:
            proceso = await asyncio.create_subprocess_exec(
                *comando.argv,
                cwd=self.cfg.workdir_abs,
                env=comando.env,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                # Una linea de stream-json puede pasar del limite por defecto
                # (64 KB) -- un tool_result con un archivo o un log grande
                # viaja como UNA linea; readline() relanza LimitOverrunError y
                # el turno entero moria.
                limit=64 * 1024 * 1024,
            )
        except OSError as e:
            await self.enviar(
                {
                    "type": "error",
                    "task_id": task_id,
                    "message": f"No se pudo lanzar el CLI ({' '.join(self.adaptador.cmd)}) en {self.cfg.workdir_abs}: {e}",
                }
            )
            return

        self._procesos[task_id] = proceso
        stderr_buf = bytearray()

        async def leer_stderr():
            # Concurrente con stdout: si nadie drena el pipe y el CLI escribe
            # mas que su buffer, se bloquea. Solo se conserva la cola.
            while True:
                trozo = await proceso.stderr.read(4096)
                if not trozo:
                    return
                stderr_buf.extend(trozo)
                if len(stderr_buf) > self.cfg.tope_stderr:
                    del stderr_buf[: len(stderr_buf) - self.cfg.tope_stderr]

        lector_err = asyncio.create_task(leer_stderr())
        try:
            while True:
                linea = await proceso.stdout.readline()
                if not linea:
                    break
                crudo = linea.decode("utf-8", errors="replace").strip()
                if not crudo:
                    continue
                if len(crudo) > self.cfg.tope_evento:
                    # Ragnar ignora los tipos que no conoce: se avisa que hubo
                    # algo en vez de tumbar el socket con un frame gigante.
                    await self.enviar({"type": "event", "task_id": task_id, "raw": {"type": "oversize", "bytes": len(crudo)}})
                    continue
                try:
                    evento = json.loads(crudo)
                except json.JSONDecodeError:
                    continue  # linea suelta que no es del protocolo
                if isinstance(evento, dict):
                    # El traductor convierte lo que emite el CLI al formato de
                    # Claude que Ragnar espera (para Claude no toca nada).
                    for raw in traductor.evento(evento):
                        await self.enviar({"type": "event", "task_id": task_id, "raw": raw})
            codigo = await proceso.wait()
            await lector_err
            stderr = bytes(stderr_buf).decode("utf-8", errors="replace")
            for raw in traductor.fin(codigo, stderr):
                await self.enviar({"type": "event", "task_id": task_id, "raw": raw})
            await self.enviar(
                {"type": "done", "task_id": task_id, "exit_code": codigo, "stderr": stderr}
            )
        except asyncio.CancelledError:
            await self._matar_proceso(proceso)
            raise
        except Exception:
            log.exception("El turno %s se rompio.", task_id)
            await self._matar_proceso(proceso)
            try:
                await self.enviar({"type": "error", "task_id": task_id, "message": "El bridge fallo a mitad del turno."})
            except Exception:
                pass
        finally:
            lector_err.cancel()
            self._procesos.pop(task_id, None)

    # ---- corte de procesos

    @staticmethod
    async def _matar_proceso(proceso: asyncio.subprocess.Process) -> None:
        if proceso.returncode is not None:
            return
        try:
            proceso.terminate()
            await asyncio.wait_for(proceso.wait(), 5)
        except asyncio.TimeoutError:
            proceso.kill()
            await proceso.wait()
        except ProcessLookupError:
            pass

    async def _matar(self, task_id: str) -> None:
        # El bucle de _turno ve el EOF de stdout y manda el `done` con el
        # codigo de salida real; aca solo se corta el proceso.
        proceso = self._procesos.get(task_id)
        if proceso is not None:
            await self._matar_proceso(proceso)

    async def _cortar_todo(self) -> None:
        for tarea in list(self._tareas.values()):
            tarea.cancel()
        if self._tareas:
            await asyncio.gather(*self._tareas.values(), return_exceptions=True)


async def ejecutar(cfg: Config, estado_dir: Optional[Path] = None) -> None:
    """Se conecta a Ragnar y reconecta con backoff exponencial hasta que lo
    frenen. Levanta ErrorFatal si Ragnar rechaza la credencial."""
    bridge = Bridge(cfg, estado_dir)
    espera = 1.0
    while True:
        try:
            async with connect(
                cfg.url,
                max_size=MAX_FRAME,
                ping_interval=20,
                ping_timeout=20,
                open_timeout=15,
            ) as ws:
                espera = 1.0
                await bridge.sesion(ws)
            log.info("Ragnar cerro la conexion.")
        except ErrorFatal:
            raise
        except (OSError, WebSocketException, asyncio.TimeoutError) as e:
            log.warning("Sin conexion con Ragnar (%s: %s).", type(e).__name__, e)
        # Jitter: si Ragnar se reinicia, todos los bridges reconectan a la vez.
        await asyncio.sleep(espera + random.uniform(0, espera / 2))
        espera = min(espera * 2, 60.0)


async def probar_conexion(cfg: Config) -> str:
    """Abre el socket, se autentica y se desconecta, sin correr ningun turno
    (no gasta cuota). Devuelve el nombre del servidor segun Ragnar; levanta
    ErrorFatal si Ragnar rechaza la credencial, o el error de red que sea."""
    adaptador = crear_adaptador(cfg, ruta_por_defecto().parent)
    async with connect(cfg.url, max_size=MAX_FRAME, open_timeout=15) as ws:
        await ws.send(
            json.dumps(
                {
                    "type": "auth",
                    "token": cfg.token,
                    "protocol": PROTOCOLO,
                    "version": __version__,
                    "agent": adaptador.nombre,
                    "cli_version": adaptador.version(),
                }
            )
        )
        respuesta = json.loads(await asyncio.wait_for(ws.recv(), 15))
    if respuesta.get("type") == "error":
        raise ErrorFatal(respuesta.get("message") or respuesta.get("code"))
    return str(respuesta.get("nombre") or "")
