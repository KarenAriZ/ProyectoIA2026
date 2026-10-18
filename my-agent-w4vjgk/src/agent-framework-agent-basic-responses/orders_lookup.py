"""Selección de datos de pedidos. Sin llamadas de red ni datos de cliente en salidas."""
import re
import unicodedata
from datetime import date, datetime
from orders_dates import COLUMNA_PREVISTO, cabeceras_con_previsto, estimar_fecha
DEFAULT_DATE_COLUMNS = (
    "fecha compromiso entrega",
    "FECHA REPROGRAMADA CONTINGENCIA FINAL",
    "3era Fecha Reprogramada",
)

ESTADO_RECEPCIONADO = "Pedido recepcionado con éxito"
ESTADO_STOCK_FABRICA = "Pedido recepcionado con éxito y pendiente de avance para entrega"
ESTADO_PRODUCCION = "En producción"
ESTADO_CONTACTO = "Próximo contacto de logística"


def normalizar_etapa(value):
    text = unicodedata.normalize("NFKD", texto(value))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).casefold().split())


def estado_produccion(etapa):
    """Reglas confirmadas por el usuario; etapas no definidas quedan pendientes."""
    etapa = normalizar_etapa(etapa)
    if etapa == "corte":
        return ESTADO_RECEPCIONADO
    if etapa == "stock fabrica":
        return ESTADO_STOCK_FABRICA
    if etapa in {"plegado", "partes y piezas", "armado", "mig", "entregado a pintura", "pintura", "montaje"}:
        return ESTADO_PRODUCCION
    if etapa in {"calidad", "bodega"}:
        return ESTADO_CONTACTO
    return "Pendiente de confirmar"


def texto(value):
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.strftime("%d-%m-%Y")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def validar_busqueda(nv="", correo=""):
    if not isinstance(nv, str) or not isinstance(correo, str):
        return {"resultado": "consulta_invalida"}
    if not nv.strip() and not correo.strip():
        return {"resultado": "consulta_invalida"}
    if len(nv) > 64:
        return {"resultado": "nv_invalido"}
    if correo and (len(correo) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", correo.strip())):
        return {"resultado": "correo_invalido"}
    return None


def buscar_pedido(headers, rows, nv="", correo=""):
    error = validar_busqueda(nv, correo)
    if error:
        return error
    names = [texto(v) for v in headers]
    if names.count("NV") != 1:
        raise ValueError("Columna NV ausente o duplicada")
    ni = names.index("NV")
    rows = list(rows)
    if correo.strip():
        if names.count("Correo") != 1:
            return {"resultado": "correo_no_disponible"}
        ci = names.index("Correo")
        target = correo.strip().casefold()
        rows = [r for r in rows if ci < len(r) and texto(r[ci]).casefold() == target]
        numeros = sorted({texto(r[ni]) for r in rows if ni < len(r) and texto(r[ni])})
        if not numeros:
            return {"resultado": "no_encontrado"}
        if not nv.strip():
            if len(numeros) > 1:
                # No revelar estados ni filas completas al seleccionar el pedido.
                return {"resultado": "varios_pedidos", "numeros_pedido": numeros[:20],
                        "total": len(numeros)}
            nv = numeros[0]
    return lookup_rockers_order(names, rows, nv.strip())

def lookup_rockers_order(headers, rows, nv):
    """Fecha aproximada = Previsto de T + tres días hábiles. No usar otras fechas."""
    names = [texto(h) for h in headers]
    if len(names) > 19 and names[19].casefold() == "previsto":
        names = cabeceras_con_previsto(names)
    date_column = COLUMNA_PREVISTO if COLUMNA_PREVISTO in names else ""
    return lookup_order(names, rows, nv, date_column=date_column, estimar_habiles=True)

def lookup_order(headers, rows, nv, date_column="", *, date_columns=(), estimar_habiles=False):
    if not isinstance(nv, str) or not nv.strip() or len(nv) > 64:
        return {"resultado": "nv_invalido"}
    names = [texto(value) for value in headers]
    def index(name):
        matches = [i for i, value in enumerate(names) if value == name]
        if len(matches) != 1:
            raise ValueError("Columna requerida ausente o duplicada: " + name)
        return matches[0]
    nv_index = index("NV")
    status_index = index("Estado Logistica")
    production_indexes = [i for i, name in enumerate(names) if normalizar_etapa(name) == "produccion"]
    if len(production_indexes) > 1:
        raise ValueError("Columna Produccion duplicada")
    production_index = production_indexes[0] if production_indexes else None
    columns = tuple(date_columns) if date_columns else ((date_column,) if date_column else ())
    date_indexes = [index(name) for name in columns]
    def cell(row, position):
        if position is None or position >= len(row) or row[position] is None:
            return ""
        return texto(row[position])
    def effective_date(row):
        selected = ""
        for position in date_indexes:
            value = cell(row, position)
            if value:
                selected = value
        return estimar_fecha(selected) if estimar_habiles else selected
    def effective_status(row):
        # Logística describe fases posteriores y tiene prioridad si está informada.
        # No devolver un pedido entregado a producción por una fórmula anterior.
        logistic_status = cell(row, status_index)
        if logistic_status:
            return logistic_status
        return estado_produccion(cell(row, production_index))
    # Exacto: no quitar puntos, ceros iniciales o separadores sin aprobación.
    matches = [row for row in rows if cell(row, nv_index) == nv.strip()]
    if not matches:
        return {"resultado": "no_encontrado"}
    values = {(cell(row, nv_index), effective_status(row), effective_date(row)) for row in matches}
    if len(values) != 1:
        return {"resultado": "requiere_revision"}
    number, status, date = values.pop()
    return {
        "numero_pedido": number,
        "estado": status or "Pendiente de confirmar",
        "fecha_aproximada": date or "Pendiente de confirmar",
    }
