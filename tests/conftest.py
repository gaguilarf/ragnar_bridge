import pytest
from websockets.asyncio.server import serve

from helpers import FakeRagnar


@pytest.fixture
async def ragnar():
    servidor = FakeRagnar()
    async with serve(servidor._handler, "127.0.0.1", 0) as srv:
        servidor.url = f"ws://127.0.0.1:{srv.sockets[0].getsockname()[1]}"
        yield servidor
