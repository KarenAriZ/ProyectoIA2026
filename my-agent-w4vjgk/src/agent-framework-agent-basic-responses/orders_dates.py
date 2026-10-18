"""Fechas del proyecto: columna T más tres días hábiles, de lunes a viernes.

No se descuenta ningún calendario de feriados. La fecha de comparación usa
UTC-5 (hora de Lima); no depende de la zona horaria del proceso de Windows.
"""
from datetime import date, datetime, timedelta, timezone

COLUMNA_PREVISTO = "Previsto produccion columna T"


def cabeceras_con_previsto(headers):
    names = [str(v).strip() if v is not None else "" for v in headers]
    if len(names) <= 19 or names[19].casefold() != "previsto":
        raise ValueError("Se esperaba el encabezado Previsto en la columna T")
    names[19] = COLUMNA_PREVISTO
    return names


def leer_fecha(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    for pattern in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value.strip(), pattern).date()
        except ValueError:
            pass
    return None


def sumar_habiles(base, cantidad=3):
    result = base
    while cantidad > 0:
        result += timedelta(days=1)
        if result.weekday() < 5:
            cantidad -= 1
    return result


def estimar_fecha(value):
    base = leer_fecha(value)
    return sumar_habiles(base).strftime("%d-%m-%Y") if base else ""


def hoy_lima():
    return datetime.now(timezone(timedelta(hours=-5))).date()


def requiere_aviso(fecha, hoy=None):
    parsed = leer_fecha(fecha)
    return parsed is not None and parsed <= sumar_habiles(hoy or hoy_lima(), 3)


def fecha_amable(value):
    parsed = leer_fecha(value)
    if parsed is None:
        return None
    meses = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
    return f"{parsed.day} de {meses[parsed.month - 1]} de {parsed.year}"


def limites_entrega(value):
    """Cinco días hábiles inclusivos desde la fecha ya calculada de T + 3."""
    inicio = leer_fecha(value)
    return (inicio, sumar_habiles(inicio, 4)) if inicio else None


def rango_amable(value):
    limites = limites_entrega(value)
    if limites is None:
        return None
    inicio, fin = limites
    if inicio.year != fin.year:
        return f"entre el {fecha_amable(inicio)} y el {fecha_amable(fin)}"
    if inicio.month != fin.month:
        inicio_sin_ano = fecha_amable(inicio).rsplit(" de ", 1)[0]
        return f"entre el {inicio_sin_ano} y el {fecha_amable(fin)}"
    return f"entre el {inicio.day} y el {fecha_amable(fin)}"
