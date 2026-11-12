"""Tiny stdio MCP client: talks to studio_mcp.py exactly the way a host does (initialize, list_tools, call_tool)."""
import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = Path(__file__).with_name('studio_mcp.py')


@asynccontextmanager
async def session(env=None):
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)], env={**os.environ, **(env or {})})
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            yield s


async def call(s, name, args):
    res = await s.call_tool(name, args)
    if res.structuredContent is not None:
        data = res.structuredContent
        return data.get('result', data) if isinstance(data, dict) and set(data) == {'result'} else data
    return json.loads(res.content[0].text)
