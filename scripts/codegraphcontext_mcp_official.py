import asyncio
import os
import sys
from importlib.metadata import PackageNotFoundError, version as pkg_version

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server


CODEGRAPHCONTEXT_SITE_PACKAGES = r"C:\Users\45485456N\.codex\mcp-tools\py-venv\Lib\site-packages"

if CODEGRAPHCONTEXT_SITE_PACKAGES not in sys.path:
    sys.path.insert(0, CODEGRAPHCONTEXT_SITE_PACKAGES)

os.environ.setdefault("CGC_RUNTIME_DB_TYPE", "kuzudb")
os.environ.setdefault("DEFAULT_DATABASE", "kuzudb")

from codegraphcontext.server import MCPServer as CodeGraphContextServer


def _server_version() -> str:
    try:
        return pkg_version("codegraphcontext")
    except PackageNotFoundError:
        return "unknown"


app = Server("CodeGraphContext")
_cgc_server: CodeGraphContextServer | None = None


def _get_cgc_server() -> CodeGraphContextServer:
    global _cgc_server
    if _cgc_server is None:
        _cgc_server = CodeGraphContextServer(loop=asyncio.get_running_loop())
    return _cgc_server


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    server = _get_cgc_server()
    tools: list[types.Tool] = []
    for definition in server.tools.values():
        tools.append(
            types.Tool(
                name=definition["name"],
                description=definition.get("description", ""),
                inputSchema=definition.get("inputSchema", {"type": "object", "properties": {}}),
            )
        )
    return tools


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> dict:
    server = _get_cgc_server()
    result = await server.handle_tool_call(name, arguments)
    if isinstance(result, dict) and "error" in result:
        raise RuntimeError(result["error"])
    return result


@app.list_resources()
async def list_resources() -> list[types.Resource]:
    return []


@app.list_resource_templates()
async def list_resource_templates() -> list[types.ResourceTemplate]:
    return []


async def main() -> int:
    server = _get_cgc_server()
    try:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
            )
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
