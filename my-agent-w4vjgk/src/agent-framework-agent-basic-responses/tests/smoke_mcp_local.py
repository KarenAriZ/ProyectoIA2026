import asyncio
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def check():
    server = Path(__file__).resolve().parents[1] / 'orders_mcp.py'
    params = StdioServerParameters(command=sys.executable, args=[str(server)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert {tool.name for tool in tools.tools} == {'consultar_estado_pedido', 'consultar_informacion_rockers'}
            result = await session.call_tool('consultar_estado_pedido', {'nv':'6963'})
            assert not result.isError
            print('MCP local respondió:', [getattr(c, 'text', '') for c in result.content])

if __name__ == '__main__':
    asyncio.run(asyncio.wait_for(check(), 15))
