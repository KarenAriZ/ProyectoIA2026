import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main


class LocalConfigurationTests(unittest.TestCase):
    def test_uses_only_local_model(self):
        with (
            patch.dict(os.environ, {"FOUNDRY_LOCAL_MODEL": " phi-4-mini "}, clear=True),
            patch.object(main, "create_local_client") as client,
            patch.object(main, "Agent") as agent,
            patch.object(main, "ResponsesHostServer") as server,
            patch.object(main, "MCPStreamableHTTPTool") as mcp,
        ):
            agent.return_value.__aenter__.return_value = agent.return_value
            server.return_value.run_async = AsyncMock()
            main.main()

            client.assert_called_once_with(model="phi-4-mini")
            self.assertIs(agent.call_args.kwargs["client"], client.return_value)
            self.assertEqual(
                agent.call_args.kwargs["default_options"],
                {"store": False, "max_tokens": 768},
            )
            self.assertEqual(agent.call_args.kwargs["tools"], [mcp.return_value])
            prepare_options = server.call_args.kwargs["prepare_options"]
            self.assertEqual(
                prepare_options(
                    object(), {"model": "inspector-alias", "max_tokens": 12}
                ),
                {"max_tokens": 12},
            )
            mcp.assert_called_once_with(
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
            server.assert_called_once_with(
                agent.return_value,
                prepare_options=main._configured_local_model_options,
            )
            server.return_value.run_async.assert_awaited_once_with()
            agent.return_value.__aexit__.assert_awaited_once_with(None, None, None)

    def test_missing_or_blank_local_model_fails_even_with_azure_configuration(self):
        for value in (None, "", "   "):
            environment = {
                "AZURE_AI_MODEL_DEPLOYMENT_NAME": "cloud-model",
                "FOUNDRY_MODEL_NAME": "cloud-model",
                "FOUNDRY_PROJECT_ENDPOINT": "https://example.invalid",
            }
            if value is not None:
                environment["FOUNDRY_LOCAL_MODEL"] = value
            with (
                self.subTest(value=value),
                patch.dict(os.environ, environment, clear=True),
                patch.object(main, "create_local_client") as client,
            ):
                with self.assertRaisesRegex(RuntimeError, "FOUNDRY_LOCAL_MODEL"):
                    main.main()
                client.assert_not_called()

    def test_local_runtime_failure_is_not_hidden(self):
        with (
            patch.dict(os.environ, {"FOUNDRY_LOCAL_MODEL": "phi-4-mini"}, clear=True),
            patch.object(main, "create_local_client", side_effect=ValueError("Unavailable model")),
            patch.object(main, "ResponsesHostServer") as server,
        ):
            with self.assertRaisesRegex(ValueError, "Unavailable model"):
                main.main()
            server.assert_not_called()

    def test_discovers_local_endpoint_and_explicitly_configures_openai_client(self):
        with (
            patch.object(main.shutil, "which", return_value="foundry.exe"),
            patch.object(main.subprocess, "run") as run,
            patch.object(
                main.subprocess,
                "check_output",
                side_effect=[
                    '{"model":{"id":"phi-4-mini-instruct-openvino-gpu:2"}}',
                    '{"running":true,"webUrls":["http://127.0.0.1:61640"]}',
                ],
            ),
            patch.object(main, "AsyncOpenAI") as openai,
            patch.object(main, "OpenAIChatCompletionClient") as client,
        ):
            main.create_local_client("phi-4-mini")
            self.assertEqual(run.call_count, 2)
            run.assert_any_call(["foundry.exe", "model", "load", "phi-4-mini"], check=True)
            openai.assert_called_once_with(
                base_url="http://127.0.0.1:61640/v1", api_key="foundry-local"
            )
            client.assert_called_once_with(
                model="phi-4-mini-instruct-openvino-gpu:2",
                async_client=openai.return_value,
            )

    def test_rejects_remote_endpoint(self):
        with (
            patch.object(main.shutil, "which", return_value="foundry.exe"),
            patch.object(main.subprocess, "run"),
            patch.object(
                main.subprocess,
                "check_output",
                side_effect=[
                    '{"model":{"id":"phi-4-mini-instruct-openvino-gpu:2"}}',
                    '{"running":true,"webUrls":["https://api.openai.com"]}',
                ],
            ),
            patch.object(main, "AsyncOpenAI") as openai,
        ):
            with self.assertRaisesRegex(RuntimeError, "loopback"):
                main.create_local_client("phi-4-mini")
            openai.assert_not_called()


class LocalTokenBudgetTests(unittest.TestCase):
    def test_inspector_output_reservation_fits_reported_input(self):
        options = main._configured_local_model_options(
            object(), {"model": "inspector-alias", "max_tokens": 2048}
        )
        self.assertEqual(options, {"max_tokens": 768})
        self.assertLessEqual(2483 + options["max_tokens"], 4096)

    def test_defaults_and_preserves_smaller_requested_limits(self):
        self.assertEqual(
            main._configured_local_model_options(object(), {}), {"max_tokens": 768}
        )
        self.assertEqual(
            main._configured_local_model_options(object(), {"max_tokens": 128, "temperature": 0.2}),
            {"max_tokens": 128, "temperature": 0.2},
        )

    def test_leaves_invalid_values_for_framework_validation(self):
        for value in (0, -1, "large", True):
            with self.subTest(value=value):
                self.assertEqual(
                    main._configured_local_model_options(object(), {"max_tokens": value}),
                    {"max_tokens": value},
                )


class MCPLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_customer_mode_exposes_only_orders_mcp(self):
        with (
            patch.dict(os.environ, {"ROCKERS_LOCAL_ORDERS_MCP": "1", "ROCKERS_ENABLE_LEARN_MCP": "0"}, clear=True),
            patch.object(main, "MCPStdioTool") as orders,
            patch.object(main, "MCPStreamableHTTPTool") as docs,
            patch.object(main, "Agent") as agent,
            patch.object(main, "ResponsesHostServer") as server,
        ):
            agent.return_value.__aenter__.return_value = agent.return_value
            server.return_value.run_async = AsyncMock()
            await main.serve_agent(None)
            self.assertEqual(agent.call_args.kwargs["tools"], [orders.return_value])
            self.assertIn("correo", agent.call_args.kwargs["instructions"])
            self.assertEqual(agent.call_args.kwargs["instructions"].count("SEGUIMIENTO DE PEDIDOS"), 1)
            docs.assert_not_called()

    async def test_closes_agent_context_when_server_fails(self):
        with (
            patch.object(main, "MCPStreamableHTTPTool"),
            patch.object(main, "Agent") as agent,
            patch.object(main, "ResponsesHostServer") as server,
        ):
            agent.return_value.__aenter__.return_value = agent.return_value
            failure = RuntimeError("Server failed")
            server.return_value.run_async = AsyncMock(side_effect=failure)

            with self.assertRaisesRegex(RuntimeError, "Server failed"):
                await main.serve_agent(None)

            agent.return_value.__aexit__.assert_awaited_once()
            self.assertIs(agent.return_value.__aexit__.call_args.args[1], failure)

    async def test_mcp_connection_failure_prevents_server_startup(self):
        with (
            patch.object(main, "MCPStreamableHTTPTool"),
            patch.object(main, "Agent") as agent,
            patch.object(main, "ResponsesHostServer") as server,
        ):
            agent.return_value.__aenter__.side_effect = RuntimeError("MCP unavailable")
            with self.assertRaisesRegex(RuntimeError, "MCP unavailable"):
                await main.serve_agent(None)
            server.assert_not_called()


if __name__ == "__main__":
    unittest.main()
