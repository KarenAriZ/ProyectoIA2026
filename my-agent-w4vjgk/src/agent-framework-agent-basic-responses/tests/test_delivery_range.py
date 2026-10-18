import sys
import unittest
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orders_dates import limites_entrega, rango_amable
from orders_guard import redactar
from orders_lookup import ESTADO_PRODUCCION, ESTADO_CONTACTO


class DeliveryRangeTests(unittest.TestCase):
    def test_monday_to_friday_example(self):
        self.assertEqual(limites_entrega("19-10-2026"), (date(2026, 10, 19), date(2026, 10, 23)))
        self.assertEqual(rango_amable("19-10-2026"), "entre el 19 y el 23 de octubre de 2026")

    def test_midweek_start_skips_weekend(self):
        self.assertEqual(limites_entrega("21-10-2026")[1], date(2026, 10, 27))

    def test_cross_month_and_year(self):
        self.assertEqual(rango_amable("30-10-2026"), "entre el 30 de octubre y el 5 de noviembre de 2026")
        self.assertEqual(rango_amable("30-12-2026"), "entre el 30 de diciembre de 2026 y el 5 de enero de 2027")

    def test_missing_date_does_not_invent_a_range(self):
        self.assertIsNone(rango_amable("Pendiente de confirmar"))

    def test_production_notice_refers_to_range_not_guaranteed_day(self):
        answer = redactar({"numero_pedido": "DEMO", "estado": ESTADO_PRODUCCION, "fecha_aproximada": "19-10-2026"}, hoy=date(2026, 10, 16))
        self.assertIn("entre el 19 y el 23 de octubre de 2026", answer)
        self.assertIn("este rango podría cambiar", answer)
        self.assertIn("atrasados con la fabricación", answer)
        self.assertNotIn("fecha estimada es el", answer)

    def test_current_window_is_not_reported_as_expired(self):
        data = {"numero_pedido": "DEMO", "estado": ESTADO_CONTACTO, "fecha_aproximada": "19-10-2026"}
        answer = redactar(data, hoy=date(2026, 10, 21))
        self.assertIn("Tu entrega podría ser entre el 19 y el 23", answer)
        self.assertNotIn("ya pasó", answer)
        self.assertNotIn("atrasados", answer)

    def test_expired_window_requires_updated_estimate(self):
        answer = redactar({"numero_pedido": "DEMO", "estado": ESTADO_CONTACTO, "fecha_aproximada": "19-10-2026"}, hoy=date(2026, 10, 24))
        self.assertIn("La entrega estaba estimada", answer)
        self.assertIn("confirmar un rango actualizado", answer)


if __name__ == "__main__":
    unittest.main()
