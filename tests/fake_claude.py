"""Doble del CLI de Claude para las pruebas: emite stream-json y sale.

Emite primero un evento con su propio argv (para que el test compruebe que
flags recibio) y despues un `result`. Si el prompt contiene SLEEP se queda
colgado, para probar cancelacion y corte por desconexion. Con FAIL sale con
codigo 3 y algo en stderr.
"""

import json
import os
import sys
import time

argv = sys.argv[1:]

# Sondeos del bridge (no son turnos).
if argv == ["--version"]:
    print("fake-claude 1.0")
    sys.exit(0)
if argv == ["auth", "status"]:
    print(json.dumps({"loggedIn": os.environ.get("FAKE_CLAUDE_LOGIN", "1") == "1"}))
    sys.exit(0)

prompt = argv[-1]

print(json.dumps({"type": "system", "subtype": "init", "argv": argv}), flush=True)
if "SLEEP" in prompt:
    time.sleep(60)
if "FAIL" in prompt:
    print("boom", file=sys.stderr, flush=True)
    sys.exit(3)
print(json.dumps({"type": "result", "is_error": False, "usage": {"input_tokens": 1}}), flush=True)
