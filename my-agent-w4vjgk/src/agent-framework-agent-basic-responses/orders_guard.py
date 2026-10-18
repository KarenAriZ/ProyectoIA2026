"""Consultas transaccionales obligatorias antes de generar texto con el modelo.

El modelo local puede narrar una llamada en vez de ejecutarla. Cuando hay un
identificador explícito, esta capa ejecuta el MCP real y devuelve sus datos con
un formato controlado, tanto en Responses normal como en streaming.
"""
import json
import logging
import re
import uuid
from agent_framework import (
    AgentMiddleware, AgentResponse, AgentResponseUpdate, Content, Message, ResponseStream,
)

logger = logging.getLogger(__name__)
from orders_lookup import ESTADO_RECEPCIONADO, ESTADO_PRODUCCION, ESTADO_CONTACTO, ESTADO_STOCK_FABRICA, normalizar_etapa
from orders_dates import fecha_amable, requiere_aviso, hoy_lima, limites_entrega, rango_amable
from rockers_knowledge import detectar_temas, es_seguimiento_personal

MENSAJES_PRODUCCION = {
    ESTADO_RECEPCIONADO: "Recibimos tu pedido correctamente.",
    ESTADO_STOCK_FABRICA: "Ya recibimos tu pedido. Te contactaremos cuando avance a la etapa de entrega.",
    ESTADO_PRODUCCION: "Tu pedido ya está en producción.",
    ESTADO_CONTACTO: "Tu pedido está en la etapa final de preparación. En los próximos días deberían contactarte.",
}

EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
NUMBER = r"[0-9](?:[0-9.-]{0,30}[0-9])?"
EXPLICIT_NV = re.compile(
    r"(?:\bnv\b|\bpedido\b|\bn[uú]mero(?:\s+de\s+pedido)?)\s*"
    r"(?:(?:es|el)\s+|[:#º°]\s*)?(" + NUMBER + r")(?![\w.-])", re.I,
)
FOLLOWUP = re.compile(r"\b(estado|fecha|pedido|consulta|consultar|buscar|busca|revisa|actualiza|llega|correo|electr[oó]nico)\b", re.I)


def extraer(text):
    correos = list(dict.fromkeys(EMAIL.findall(text)))
    sin_correo = EMAIL.sub("", text)
    numeros = list(dict.fromkeys(EXPLICIT_NV.findall(sin_correo)))
    plain = re.fullmatch(r"\s*(" + NUMBER + r")\s*", sin_correo)
    if plain and plain.group(1) not in numeros:
        numeros.append(plain.group(1))
    if len(correos) > 1 or len(numeros) > 1:
        return {"ambiguo": True}
    return {"nv": numeros[0] if numeros else "", "correo": correos[0] if correos else ""}


def ultima_seleccion_pendiente(messages):
    """Solo conservar el correo para elegir entre pedidos realmente devueltos."""
    for message in reversed(messages):
        for content in reversed(message.contents):
            if content.type == "function_result":
                data = content.result
                if isinstance(data, str):
                    try:
                        data = json.loads(data)
                    except ValueError:
                        return False
                return isinstance(data, dict) and data.get("resultado") == "varios_pedidos"
    return False


def resolver(messages):
    users = [m.text for m in messages if m.role == "user" and m.text]
    if not users:
        return None
    current = extraer(users[-1])
    if current.get("ambiguo"):
        return current
    if current["nv"] or current["correo"]:
        if current["nv"] and not current["correo"] and ultima_seleccion_pendiente(messages[:-1]):
            for text in reversed(users[:-1]):
                previous = extraer(text)
                if previous.get("correo"):
                    current["correo"] = previous["correo"]
                    break
        return current
    if FOLLOWUP.search(users[-1]):
        for text in reversed(users[:-1]):
            previous = extraer(text)
            if previous.get("nv") or previous.get("correo"):
                return previous
        return {"falta_dato": True}
    return None


def interpretar(raw):
    if isinstance(raw, str):
        data = json.loads(raw)
    else:
        texts = [c.text for c in raw if c.type == "text" and c.text]
        data = json.loads("\n".join(texts))
    if not isinstance(data, dict):
        raise ValueError("Respuesta MCP no válida")
    return data


def redactar(data, hoy=None):
    if "numero_pedido" in data:
        nv = str(data["numero_pedido"])
        estado = data.get("estado") or "Pendiente de confirmar"
        fecha = data.get("fecha_aproximada") or "Pendiente de confirmar"
        logistic = normalizar_etapa(estado)
        if logistic == "entregado":
            return f"Tu pedido {nv} figura como entregado. Si necesitas revisar algún detalle de la entrega, el equipo de atención puede ayudarte."
        if logistic == "cancelado":
            return f"Tu pedido {nv} figura como cancelado. Si necesitas más información, el equipo de atención puede ayudarte."
        if estado == "Pendiente de confirmar" and not fecha_amable(fecha):
            return (f"Encontré tu pedido {nv}. Por ahora no tengo confirmados su estado ni una fecha estimada. "
                    "El equipo de logística puede ayudarte a aclararlo.")
        message = MENSAJES_PRODUCCION.get(estado)
        if message is None:
            if logistic == "en ruta":
                message = "Tu pedido está en ruta."
            elif logistic in {"coordinacion", "coordinacion logistica"}:
                message = "Estamos coordinando el despacho de tu pedido."
            elif estado == "Pendiente de confirmar":
                message = "Por ahora no tengo confirmado en qué etapa está tu pedido."
            else:
                message = f"El estado de tu pedido es: {estado}."
        friendly_range = rango_amable(fecha)
        limites = limites_entrega(fecha)
        rango_vencido = limites is not None and limites[1] < (hoy or hoy_lima())
        production_pending = estado in {ESTADO_RECEPCIONADO, ESTADO_PRODUCCION, ESTADO_STOCK_FABRICA}
        if production_pending and requiere_aviso(fecha, hoy=hoy):
            if rango_vencido:
                date_message = f"La entrega estaba estimada {friendly_range}. "
            else:
                date_message = f"La entrega está estimada {friendly_range}, aunque este rango podría cambiar. "
            date_message += ("Estamos atrasados con la fabricación y estamos haciendo todo lo posible para ponernos al día. "
                             "Sentimos la espera y agradecemos tu paciencia.")
        elif friendly_range and rango_vencido:
            date_message = (f"La entrega estaba estimada {friendly_range}. "
                            "Como ese rango ya pasó, el equipo de logística debe confirmar un rango actualizado.")
        elif friendly_range:
            date_message = f"Tu entrega podría ser {friendly_range}. Es un rango estimado."
        else:
            date_message = "Todavía no tenemos un rango estimado de entrega confirmado."
        return f"Ya revisé tu pedido {nv}. {message}\n\n{date_message}"
    outcome = data.get("resultado")
    if outcome == "varios_pedidos":
        numbers = ", ".join(str(n) for n in data.get("numeros_pedido", []))
        return f"Veo varios pedidos asociados a ese correo: {numbers}. ¿Cuál te gustaría revisar?"
    if outcome == "no_encontrado":
        return "No pude encontrar un pedido con ese dato. ¿Me confirmas el número de pedido o el correo con el que hiciste la compra?"
    if outcome == "requiere_revision":
        return "Encontré tu pedido, pero hay información que necesita revisión. Para darte una respuesta correcta, el equipo de logística deberá confirmarla."
    if outcome == "correo_no_disponible":
        return "Por ahora no puedo localizarlo por correo. ¿Me compartes el número de tu pedido para ayudarte?"
    if outcome in {"correo_invalido", "nv_invalido", "consulta_invalida"}:
        return "Parece que el dato está incompleto. ¿Me compartes de nuevo el número de pedido o tu correo de compra?"
    return "En este momento no puedo verificar cómo va tu pedido. Por favor, inténtalo de nuevo en unos minutos o comunícate con el equipo de atención."


class PedidosObligatorios(AgentMiddleware):
    def __init__(self, tool):
        self.tool = tool

    async def process(self, context, call_next):
        query = resolver(context.messages)
        users = [m.text for m in context.messages if m.role == "user" and m.text]
        latest = users[-1] if users else ""
        temas = detectar_temas(latest)
        if temas and not es_seguimiento_personal(latest, extraer(latest)) and not (query or {}).get("ambiguo"):
            query = {"temas": temas}
        if query is None:
            await call_next()
            return
        messages = []
        if query.get("temas"):
            answers = []
            for tema in query["temas"]:
                call_id = "call_" + uuid.uuid4().hex
                args = {"tema": tema}
                messages.append(Message("assistant", [Content.from_function_call(
                    call_id=call_id, name="consultar_informacion_rockers", arguments=args)]))
                try:
                    raw = await self.tool.call_tool("consultar_informacion_rockers", **args)
                    data = interpretar(raw)
                    logger.info("MCP información Rockers ejecutado; tema=%s", tema)
                except Exception:
                    data = {"resultado": "informacion_no_disponible"}
                messages.append(Message("tool", [Content.from_function_result(call_id=call_id, result=data)]))
                answers.append(data.get("respuesta") or "Por ahora no tengo esa información confirmada. Puedes consultarla con el equipo en info@rockers.cl.")
            answer = "\n\n".join(answers)
        elif query.get("ambiguo"):
            answer = "Claro, te ayudo. Para revisar el pedido correcto, envíame un solo número de pedido o correo a la vez."
        elif query.get("falta_dato"):
            answer = "¡Claro, con gusto te ayudo! ¿Me compartes el número de tu pedido o el correo con el que hiciste la compra?"
        else:
            call_id = "call_" + uuid.uuid4().hex
            args = {"nv": query["nv"], "correo": query["correo"]}
            messages.append(Message("assistant", [Content.from_function_call(
                call_id=call_id, name="consultar_estado_pedido", arguments=args)]))
            try:
                raw = await self.tool.call_tool("consultar_estado_pedido", **args)
                data = interpretar(raw)
                logger.info("MCP pedidos ejecutado; resultado=%s", data.get("resultado", "encontrado"))
            except Exception:
                logger.warning("Falló la consulta al MCP de pedidos")
                data = {"resultado": "error_consulta"}
            messages.append(Message("tool", [Content.from_function_result(call_id=call_id, result=data)]))
            answer = redactar(data)
        messages.append(Message("assistant", [answer]))
        if not context.stream:
            context.result = AgentResponse(messages=messages)
            return

        async def updates():
            response_id = "resp_" + uuid.uuid4().hex
            for message in messages:
                yield AgentResponseUpdate(role=message.role, contents=message.contents,
                    response_id=response_id, message_id=message.message_id or uuid.uuid4().hex)
        context.result = ResponseStream(updates(), finalizer=AgentResponse.from_updates)
