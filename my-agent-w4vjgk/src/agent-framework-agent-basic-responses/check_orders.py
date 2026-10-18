"""Comprueba acceso y estructura sin mostrar filas ni datos personales."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))


def main():
    from orders_drive import cargar_primera_hoja
    from orders_lookup import texto
    from orders_dates import COLUMNA_PREVISTO
    headers, rows = cargar_primera_hoja(os.environ["ROCKERS_SHEET_ID"], int(os.getenv("ROCKERS_HEADER_ROW", "2")))
    names = [texto(v) for v in headers]
    required = ["NV", "Correo", "Estado Logistica", "Produccion", COLUMNA_PREVISTO]
    if any(names.count(name) != 1 for name in required):
        raise RuntimeError("Faltan columnas requeridas o están duplicadas.")
    print("Archivo compartido accesible. Primera hoja y columnas requeridas comprobadas.")
    print("Filas leídas:", len(rows))
    print("No se han mostrado datos de clientes ni modificado el archivo.")


if __name__ == "__main__":
    main()
