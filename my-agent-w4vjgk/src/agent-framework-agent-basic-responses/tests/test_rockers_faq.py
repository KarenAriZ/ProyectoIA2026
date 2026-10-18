import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_framework import Agent, AgentContext, Content, Message
from agent_framework.openai import OpenAIChatCompletionClient
from openai import AsyncOpenAI
from orders_guard import PedidosObligatorios
from rockers_knowledge import consultar_informacion, detectar_temas


class FAQTests(unittest.TestCase):
    def test_common_queries(self):
        queries = {
            "¿Hacen envíos a regiones?": "despachos",
            "¿Cuánto cuesta el despacho?": "tarifas",
            "¿Qué plazo de entrega tienen?": "plazos",
            "¿Puedo pagar con tarjeta?": "pagos",
            "¿Pueden emitir factura?": "comprobantes",
            "¿Tienen productos de pronta entrega?": "pronta_entrega",
            "¿Dónde están ubicados?": "ubicacion",
            "Quiero agendar una visita": "visitas",
            "¿Los muebles vienen armados?": "armado",
            "¿Puedo pedir uno a medida?": "personalizacion",
            "Quiero hablar con un asesor": "contacto",
            "¿Cuál es su horario de atención?": "contacto",
        }
        for query, topic in queries.items():
            with self.subTest(query=query):
                self.assertIn(topic, detectar_temas(query))
                self.assertIn("respuesta", consultar_informacion(topic))

    def test_showroom_hours_are_separate_from_message_hours(self):
        self.assertIn("08:30", consultar_informacion("ubicacion")["respuesta"])
        self.assertIn("09:00", consultar_informacion("contacto")["respuesta"])
        self.assertNotIn("contacto", detectar_temas("¿Cuál es el horario del showroom?"))

    def test_does_not_guarantee_stock_or_reserve_a_visit(self):
        self.assertIn("no puedo asegurar stock", consultar_informacion("pronta_entrega")["respuesta"])
        self.assertIn("queda pendiente", consultar_informacion("visitas")["respuesta"])
        self.assertIn("no puedo transferirte", consultar_informacion("contacto")["respuesta"])

    def test_unknown_topic_does_not_invent_answer(self):
        self.assertEqual(consultar_informacion("garantia_de_10_anos"), {"resultado": "informacion_no_disponible"})

    def test_confirmed_general_timeframes_replace_old_document_times(self):
        answer = consultar_informacion("plazos")["respuesta"]
        self.assertIn("7 a 10 días hábiles", answer)
        self.assertIn("3 a 5 días hábiles", answer)
        self.assertIn("https://rockers.cl", answer)
        self.assertIn("descripción del producto", answer)
        for outdated in ("12 días", "al día siguiente", "2 días hábiles"):
            self.assertNotIn(outdated, answer)

    def test_immediate_delivery_topic_also_uses_new_range(self):
        answer = consultar_informacion("pronta_entrega")["respuesta"]
        self.assertIn("3 a 5 días hábiles", answer)
        self.assertIn("confirmar", answer)

    def test_changing_delivery_address_is_not_showroom_question(self):
        self.assertEqual(detectar_temas("Quiero cambiar la dirección de entrega"), ["contacto"])


class FAQIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def tool(self):
        t = AsyncMock()
        async def call(name, **args):
            if name == "consultar_informacion_rockers":
                data = consultar_informacion(args["tema"])
            else:
                data = {"numero_pedido": args["nv"], "estado": "En producción", "fecha_aproximada": "Pendiente de confirmar"}
            return [Content.from_text(json.dumps(data))]
        t.call_tool.side_effect = call
        return t

    async def test_faq_retrieves_information_without_querying_orders(self):
        tool = self.tool()
        ctx = AgentContext(agent=None, messages=[Message("user", ["¿Puedo pagar con tarjeta?"])])
        next_call = AsyncMock()
        await PedidosObligatorios(tool).process(ctx, next_call)
        tool.call_tool.assert_awaited_once_with("consultar_informacion_rockers", tema="pagos")
        self.assertIn("3 o 6 cuotas", ctx.result.text)
        next_call.assert_not_called()

    async def test_faq_after_an_order_does_not_repeat_lookup(self):
        tool = self.tool()
        ctx = AgentContext(agent=None, messages=[Message("user", ["Pedido 7511"]), Message("assistant", ["En producción"]), Message("user", ["¿Hacen envíos a regiones?"])])
        await PedidosObligatorios(tool).process(ctx, AsyncMock())
        tool.call_tool.assert_awaited_once_with("consultar_informacion_rockers", tema="despachos")
        self.assertNotIn("número de tu pedido", ctx.result.text)

    async def test_personal_delivery_date_still_uses_orders_mcp(self):
        tool = self.tool()
        ctx = AgentContext(agent=None, messages=[Message("user", ["¿Qué plazo de entrega tiene mi pedido 7511?"])])
        await PedidosObligatorios(tool).process(ctx, AsyncMock())
        tool.call_tool.assert_awaited_once_with("consultar_estado_pedido", nv="7511", correo="")

    async def test_identifying_delivery_type_guides_customer_to_product_description(self):
        tool = self.tool()
        ctx = AgentContext(agent=None, messages=[Message("user", ["¿Cómo sé si mi compra es de fabricación o pronta entrega?"])])
        await PedidosObligatorios(tool).process(ctx, AsyncMock())
        tool.call_tool.assert_awaited_once_with("consultar_informacion_rockers", tema="tipo_entrega")
        self.assertIn("descripción del producto", ctx.result.text)
        self.assertNotIn("número de tu pedido", ctx.result.text)

    async def test_payments_and_receipt_can_be_answered_together(self):
        tool = self.tool()
        ctx = AgentContext(agent=None, messages=[Message("user", ["¿Cómo puedo pagar y pueden emitir factura?"])])
        await PedidosObligatorios(tool).process(ctx, AsyncMock())
        self.assertIn("tarjeta", ctx.result.text)
        self.assertIn("boleta o factura", ctx.result.text)
        self.assertEqual(tool.call_tool.await_count, 2)

    async def test_agent_streaming_returns_grounded_faq_without_model_inference(self):
        tool = self.tool()
        client = OpenAIChatCompletionClient(model="test", async_client=AsyncOpenAI(base_url="http://127.0.0.1:1/v1", api_key="local", max_retries=0))
        async with Agent(client=client, middleware=[PedidosObligatorios(tool)]) as agent:
            stream = agent.run("¿Los productos vienen armados?", stream=True)
            updates = [u async for u in stream]
            response = await stream.get_final_response()
        self.assertIn("armados y listos", response.text)
        self.assertTrue(any(c.type == "function_result" for u in updates for c in u.contents))


if __name__ == "__main__":
    unittest.main()
