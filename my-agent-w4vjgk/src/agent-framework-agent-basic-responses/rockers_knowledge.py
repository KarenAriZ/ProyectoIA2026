"""Información comercial del documento aportado. No ejecuta reservas ni envíos."""
import json
import re
import unicodedata
from pathlib import Path

BASE = Path(__file__).with_name("rockers_faq.json")


def consultar_informacion(tema):
    data = json.loads(BASE.read_text(encoding="utf-8"))
    respuesta = data["temas"].get(tema)
    return {"tema": tema, "respuesta": respuesta} if respuesta else {"resultado": "informacion_no_disponible"}


def normalizar(text):
    value = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(c for c in value if not unicodedata.combining(c)).split())


PATRONES = (
    ("visitas", r"agend|reserv|\bvisita[rs]?\b|visitar"),
    ("ubicacion", r"ubicad|direccion|showroom|san fernando|donde (?:estan|queda|se encuentran|puedo retirar)"),
    ("armado", r"\barmad[oa]s?\b|\barmar\b|\bensambl"),
    ("personalizacion", r"personaliz|a medida|medidas? especial|color especial|otro color"),
    ("pagos", r"\bpagar\b|\bpagos?\b|tarjetas?|credito|debito|transferencia|cuotas?"),
    ("comprobantes", r"boletas?|facturas?|comprobantes?"),
    ("pronta_entrega", r"pronta entrega|\bstock\b|disponibil|disponibles?|entrega inmediata"),
    ("tarifas", r"tarifas?|(?:valor|costo|precio).*(?:envio|despacho)|cuanto.*cuesta.*(?:envio|despacho)"),
    ("plazos", r"\bplazos?\b|cuanto.*(?:demora|tarda)|cuantos dias|tiempo.*entrega|retiro.*dias"),
    ("despachos", r"\benvian\b|\benvios?\b|\bdespachos?\b|\bregiones?\b"),
    ("contacto", r"asesor|hablar.*persona|atencion.*human|whatsapp|contacto|contactar|telefono|logistica|horario|a que hora|otra[s]? consulta|otra[s]? duda"),
    ("encuesta", r"encuesta|evaluar.*experiencia|opinar.*compra"),
)


def detectar_temas(text):
    text = normalizar(text)
    if re.search(r"(?:tipo|modalidad).*entrega|(?:fabricacion.*pronta entrega|pronta entrega.*fabricacion)|(?:como se|saber|identificar|corresponde).*pronta entrega", text):
        return ["tipo_entrega"]
    if re.search(r"(?:cambiar|modificar|corregir).*direccion", text):
        return ["contacto"]
    temas = [name for name, pattern in PATRONES if re.search(pattern, text)]
    if "visitas" in temas and "ubicacion" in temas:
        temas.remove("ubicacion")
    if "contacto" in temas and any(t in temas for t in ("visitas", "ubicacion")):
        temas.remove("contacto")
    if "tarifas" in temas and "despachos" in temas:
        temas.remove("despachos")
    if "plazos" in temas and "despachos" in temas:
        temas.remove("despachos")
    return temas[:3]


def es_seguimiento_personal(text, query):
    text = normalizar(text)
    if "tipo_entrega" in detectar_temas(text):
        return False
    referencia = bool(query and (query.get("nv") or query.get("correo"))) or bool(re.search(r"\bmi (?:pedido|compra)\b", text))
    return referencia and bool(re.search(r"estado|seguimiento|donde esta|cuando llega|avance|fecha|entrega|demora|plazo", text))


def instrucciones_conocimiento():
    data = json.loads(BASE.read_text(encoding="utf-8"))
    return ("\nINFORMACIÓN COMERCIAL DISPONIBLE\nUsa exclusivamente estos datos para consultas generales. "
            "No los presentes como estado de un pedido concreto, stock actual o una gestión realizada. "
            "No menciones el documento de origen al cliente.\n" +
            "\n".join(f"{tema}: {respuesta}" for tema, respuesta in data["temas"].items()))
