"""Prueba interna: muestra encabezados, nunca filas de clientes."""
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).with_name(".env"))

def main():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    credentials = service_account.Credentials.from_service_account_file(
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    tab = "'" + os.environ["ROCKERS_SHEET_TAB"].replace("'", "''") + "'"
    header_row = int(os.getenv("ROCKERS_HEADER_ROW", "2"))
    if header_row < 1:
        raise ValueError("ROCKERS_HEADER_ROW debe ser mayor que cero.")
    result = service.spreadsheets().values().get(
        spreadsheetId=os.environ["ROCKERS_SHEET_ID"], range=f"{tab}!{header_row}:{header_row}"
    ).execute()
    rows = result.get("values", [])
    if not rows:
        raise RuntimeError("Fila de encabezados vacía: verifica pestaña y ROCKERS_HEADER_ROW.")
    print("Conexión correcta. Encabezados:", rows[0])

if __name__ == "__main__":
    main()
