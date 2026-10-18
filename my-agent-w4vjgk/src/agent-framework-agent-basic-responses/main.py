# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from agent_framework import Agent, MCPStreamableHTTPTool, MCPStdioTool
from agent_framework.openai import OpenAIChatCompletionClient
from agent_framework_foundry_hosting import ResponsesHostServer
from dotenv import load_dotenv
from openai import AsyncOpenAI
from orders_guard import PedidosObligatorios
from rockers_knowledge import instrucciones_conocimiento

# Load environment variables from .env file
load_dotenv(Path(__file__).with_name(".env"))


# Leave room for instructions, tools and history in the 4096-token local context.
LOCAL_MAX_OUTPUT_TOKENS = 768


def _configured_local_model_options(
    _request: object, options: dict[str, Any]
) -> dict[str, Any]:
    configured = {name: value for name, value in options.items() if name != "model"}
    requested = configured.get("max_tokens")
    if requested is None:
        configured["max_tokens"] = LOCAL_MAX_OUTPUT_TOKENS
    elif isinstance(requested, int) and not isinstance(requested, bool) and requested > 0:
        configured["max_tokens"] = min(requested, LOCAL_MAX_OUTPUT_TOKENS)
    return configured


def create_local_client(model: str) -> OpenAIChatCompletionClient:
    executable = shutil.which("foundry")
    if not executable:
        raise RuntimeError("Foundry Local CLI is not installed or not on PATH.")

    model_info = json.loads(
        subprocess.check_output(
            [executable, "model", "info", model, "--output", "json"],
            encoding="utf-8",
        )
    )
    model_config = model_info.get("model")
    model_id = model_config.get("id") if isinstance(model_config, dict) else None
    if not isinstance(model_id, str) or not model_id:
        raise RuntimeError(f"Foundry Local did not report an API model ID for {model}.")

    subprocess.run([executable, "server", "start"], check=True)
    subprocess.run([executable, "model", "load", model], check=True)
    status = json.loads(
        subprocess.check_output(
            [executable, "server", "status", "--output", "json"], encoding="utf-8"
        )
    )
    urls = status.get("webUrls")
    if not status.get("running") or not isinstance(urls, list) or not urls:
        raise RuntimeError("Foundry Local did not report a running HTTP server.")
    endpoint = urls[0]
    if not isinstance(endpoint, str):
        raise RuntimeError("Foundry Local reported an invalid endpoint.")
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in ("127.0.0.1", "localhost", "::1")
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise RuntimeError("Foundry Local endpoint must be a loopback HTTP address.")

    return OpenAIChatCompletionClient(
        model=model_id,
        async_client=AsyncOpenAI(
            base_url=f"{endpoint.rstrip('/')}/v1",
            api_key="foundry-local",
        ),
    )


def main():
    model_name = os.getenv("FOUNDRY_LOCAL_MODEL", "").strip()
    if not model_name:
        raise RuntimeError(
            "Local model is not configured. Set FOUNDRY_LOCAL_MODEL."
        )

    client = create_local_client(model=model_name)

    asyncio.run(serve_agent(client))


async def serve_agent(client: OpenAIChatCompletionClient) -> None:
    instructions_path = Path(__file__).with_name("rockers_instructions.txt")
    rockers_instructions = instructions_path.read_text(encoding="utf-8") + instrucciones_conocimiento()
    tools = []
    if os.getenv("ROCKERS_LOCAL_ORDERS_MCP", "").strip() == "1":
        tools.append(MCPStdioTool(
            name="Rockers Pedidos Local",
            command=sys.executable,
            args=[str(Path(__file__).with_name("orders_mcp.py"))],
            allowed_tools=["consultar_estado_pedido", "consultar_informacion_rockers"],
            load_prompts=False,
            request_timeout=30,
            approval_mode="never_require",
        ))
    orders_url = os.getenv("ROCKERS_ORDERS_MCP_URL", "").strip()
    if orders_url and tools:
        raise RuntimeError("Selecciona solo un MCP de pedidos: local o remoto.")
    if orders_url:
        parsed_orders = urlsplit(orders_url)
        if (
            parsed_orders.scheme != "https"
            or not parsed_orders.hostname
            or parsed_orders.username
            or parsed_orders.password
            or parsed_orders.query
            or parsed_orders.fragment
        ):
            raise RuntimeError("ROCKERS_ORDERS_MCP_URL must be an HTTPS endpoint without embedded credentials.")
        orders_token = os.getenv("ROCKERS_ORDERS_MCP_TOKEN", "").strip()
        if not orders_token:
            raise RuntimeError("Configure ROCKERS_ORDERS_MCP_TOKEN before enabling order access.")
        tools.append(MCPStreamableHTTPTool(
            name="Rockers Pedidos",
            url=orders_url,
            static_headers={"Authorization": f"Bearer {orders_token}"},
            allowed_tools=["consultar_estado_pedido"],
            load_prompts=False,
            request_timeout=30,
            approval_mode="always_require",
        ))
    middleware = []
    if os.getenv("ROCKERS_LOCAL_ORDERS_MCP", "").strip() == "1":
        middleware.append(PedidosObligatorios(tools[0]))
    if os.getenv("ROCKERS_ENABLE_LEARN_MCP", "1").strip() == "1":
        learn_mcp = MCPStreamableHTTPTool(
            name="Microsoft Learn",
            url="https://learn.microsoft.com/api/mcp",
            allowed_tools=[
                "microsoft_docs_search",
                "microsoft_docs_fetch",
                "microsoft_code_sample_search",
            ],
            load_prompts=False,
            request_timeout=60,
            approval_mode="never_require",
        )
        tools.insert(0, learn_mcp)

    async with Agent(
        client=client,
        instructions=rockers_instructions,
        tools=tools,
        middleware=middleware,
        # History will be managed by the hosting infrastructure, thus there
        # is no need to store history by the service. Learn more at:
        # https://developers.openai.com/api/reference/resources/responses/methods/create
        default_options={"store": False, "max_tokens": LOCAL_MAX_OUTPUT_TOKENS},
    ) as agent:
        server = ResponsesHostServer(
            agent, prepare_options=_configured_local_model_options
        )
        await server.run_async()


if __name__ == "__main__":
    main()
