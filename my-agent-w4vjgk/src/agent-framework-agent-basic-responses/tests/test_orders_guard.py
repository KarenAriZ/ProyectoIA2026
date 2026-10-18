import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_framework import Agent, AgentContext, Content, Message
from agent_framework.openai import OpenAIChatCompletionClient
from openai import AsyncOpenAI
from orders_guard import PedidosObligatorios, extraer, resolver


class ParserTests(unittest.TestCase):
    def test_request_from_screenshot(self):
        self.assertEqual(extraer("y puedes buscar por el número de pedido 7502"), {"nv": "7502", "correo": ""})

    def test_email_digits_not_mistaken_for_order(self):
        self.assertEqual(extraer("Mi correo es prueba7502@example.com"), {"nv": "", "correo": "prueba7502@example.com"})

    def test_preserves_order_format(self):
        self.assertEqual(extraer("NV 007.502")["nv"], "007.502")

    def test_plain_number(self):
        self.assertEqual(extraer("7502")["nv"], "7502")

    def test_followup_uses_user_history(self):
        messages = [Message("user", ["Consulta el pedido 7502"]), Message("assistant", ["Respuesta"]), Message("user", ["¿Y la fecha?"])]
        self.assertEqual(resolver(messages)["nv"], "7502")

    def test_assistant_cannot_invent_identifier(self):
        messages = [Message("assistant", ["Tu pedido 7502"]), Message("user", ["¿Y la fecha?"])]
        self.assertEqual(resolver(messages), {"falta_dato": True})

    def test_new_nv_does_not_reuse_failed_email(self):
        messages = [Message("user", ["prueba@example.com"]), Message("assistant", ["No encontrado"]), Message("user", ["pedido 7502"])]
        self.assertEqual(resolver(messages), {"nv": "7502", "correo": ""})

    def test_selecting_from_multiple_keeps_email(self):
        messages = [Message("user", ["prueba@example.com"]),
            Message("tool", [Content.from_function_result(call_id="1", result={"resultado": "varios_pedidos", "numeros_pedido": ["7502", "7503"]})]),
            Message("assistant", ["¿Cuál deseas consultar?"]), Message("user", ["7502"])]
        self.assertEqual(resolver(messages), {"nv": "7502", "correo": "prueba@example.com"})


class GuardTests(unittest.IsolatedAsyncioTestCase):
    def tool(self, data=None):
        tool = AsyncMock()
        import json
        tool.call_tool.return_value = [Content.from_text(json.dumps(data or {
            "numero_pedido": "7502", "estado": "Pendiente de confirmar", "fecha_aproximada": "Pendiente de confirmar"}))]
        return tool

    async def test_real_middleware_does_not_call_model_for_order(self):
        tool = self.tool()
        # Puerto sin servicio: si intenta recurrir al modelo, esta prueba falla.
        client = OpenAIChatCompletionClient(model="test", async_client=AsyncOpenAI(base_url="http://127.0.0.1:1/v1", api_key="local", max_retries=0))
        async with Agent(client=client, middleware=[PedidosObligatorios(tool)]) as agent:
            response = await agent.run("y puedes buscar por el número de pedido 7502")
        self.assertIn("Encontré tu pedido 7502", response.text)
        self.assertIn("no tengo confirmados", response.text)
        tool.call_tool.assert_awaited_once_with("consultar_estado_pedido", nv="7502", correo="")
        self.assertTrue(any(c.type == "function_call" for m in response.messages for c in m.contents))
        self.assertTrue(any(c.type == "function_result" for m in response.messages for c in m.contents))

    async def test_real_streaming_path_and_final_result(self):
        tool = self.tool()
        client = OpenAIChatCompletionClient(model="test", async_client=AsyncOpenAI(base_url="http://127.0.0.1:1/v1", api_key="local", max_retries=0))
        async with Agent(client=client, middleware=[PedidosObligatorios(tool)]) as agent:
            stream = agent.run("pedido 7502", stream=True)
            chunks = [u async for u in stream]
            final = await stream.get_final_response()
        self.assertIn("Encontré tu pedido 7502", final.text)
        self.assertTrue(any(c.type == "function_result" for u in chunks for c in u.contents))

    async def test_missing_identifier_cannot_invent_no_results(self):
        tool = self.tool()
        guard = PedidosObligatorios(tool)
        ctx = AgentContext(agent=None, messages=[Message("user", ["Quiero consultar mi pedido"])])
        next_call = AsyncMock()
        await guard.process(ctx, next_call)
        self.assertIn("número de tu pedido", ctx.result.text)
        next_call.assert_not_called()
        tool.call_tool.assert_not_called()

    async def test_connection_error_cannot_be_reported_as_not_found(self):
        tool = self.tool()
        tool.call_tool.side_effect = RuntimeError("sin conexión")
        ctx = AgentContext(agent=None, messages=[Message("user", ["pedido 7502"])])
        await PedidosObligatorios(tool).process(ctx, AsyncMock())
        self.assertIn("no puedo verificar", ctx.result.text)
        self.assertNotIn("no encontró", ctx.result.text)

    async def test_unrelated_message_continues_to_model(self):
        next_call = AsyncMock()
        ctx = AgentContext(agent=None, messages=[Message("user", ["Hola, buenos días"])])
        await PedidosObligatorios(self.tool()).process(ctx, next_call)
        next_call.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
