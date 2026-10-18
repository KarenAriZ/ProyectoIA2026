"""Adaptador de lectura; no entrega filas completas al agente."""
import os
from orders_lookup import lookup_rockers_order

def consultar_estado_pedido(nv: str) -> dict:
    if not isinstance(nv, str) or not nv.strip() or len(nv) > 64:
        return {"resultado": "nv_invalido"}
    if not all(os.getenv(k, "").strip() for k in (
        "GOOGLE_APPLICATION_CREDENTIALS", "ROCKERS_SHEET_ID", "ROCKERS_SHEET_TAB"
    )):
        return {"resultado": "configuracion_pendiente"}
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from google_auth_httplib2 import AuthorizedHttp
        import httplib2
    except ImportError:
        return {"resultado": "dependencias_pendientes"}
    try:
        credentials = service_account.Credentials.from_service_account_file(
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        service = build("sheets", "v4",
            http=AuthorizedHttp(credentials, http=httplib2.Http(timeout=20)),
            cache_discovery=False)
        tab = "'" + os.environ["ROCKERS_SHEET_TAB"].replace("'", "''") + "'"
        header_row = int(os.getenv("ROCKERS_HEADER_ROW", "2"))
        if header_row < 1:
            return {"resultado": "configuracion_pendiente"}
        # Lee un rango fijo; el NV nunca se interpola en rangos o consultas.
        result = service.spreadsheets().values().get(
            spreadsheetId=os.environ["ROCKERS_SHEET_ID"],
            range=f"{tab}!A{header_row}:AT",
            valueRenderOption="FORMATTED_VALUE",
        ).execute(num_retries=0)
    except Exception:
        # No exponer claves, rutas privadas, respuestas HTTP ni filas.
        return {"resultado": "error_consulta"}
    values = result.get("values", [])
    if not values:
        return {"resultado": "estructura_no_valida"}
    try:
        return lookup_rockers_order(values[0], values[1:], nv)
    except ValueError:
        return {"resultado": "estructura_no_valida"}
