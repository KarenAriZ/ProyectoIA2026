"""Servidor MCP local. La salida estándar está reservada al protocolo."""
from pathlib import Path
import os
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv(Path(__file__).with_name(".env"))
mcp = FastMCP("Rockers Pedidos")


@mcp.tool()
def consultar_informacion_rockers(tema: str) -> dict:
    """Consulta información general: despachos, tarifas, plazos, pagos,
    comprobantes, pronta_entrega, ubicacion, visitas, armado, personalizacion,
    contacto, encuesta o tipo_entrega. No consulta el estado de un pedido concreto.
    """
    from rockers_knowledge import consultar_informacion
    return consultar_informacion(tema)

@mcp.tool()
def consultar_estado_pedido(nv: str = "", correo: str = "") -> dict:
    """Busca un pedido por NV exacto o correo del comprador.

    Con varios pedidos por correo devuelve números para que el usuario elija.
    Solo devuelve número, estado y fecha; no acredita identidad ni modifica datos.
    """
    source = os.getenv("ROCKERS_ORDERS_SOURCE", "excel").strip()
    if source == "drive_xlsx":
        from orders_drive import consultar_estado_pedido as lookup
    elif source == "excel":
        from orders_excel import consultar_estado_pedido as lookup
    else:
        return {"resultado": "configuracion_pendiente"}
    return lookup(nv, correo)

if __name__ == "__main__":
    mcp.run(transport="stdio")
