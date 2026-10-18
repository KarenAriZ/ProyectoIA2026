import sys
import unittest
from datetime import date, datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orders_dates import COLUMNA_PREVISTO, cabeceras_con_previsto, estimar_fecha, requiere_aviso
from orders_lookup import lookup_rockers_order, ESTADO_PRODUCCION, ESTADO_CONTACTO, ESTADO_RECEPCIONADO, ESTADO_STOCK_FABRICA
from orders_guard import redactar


class DatesTests(unittest.TestCase):
    def test_friday_plus_three_business_days(self):
        self.assertEqual(estimar_fecha(datetime(2026, 10, 16)), "21-10-2026")

    def test_weekend_base_and_year_boundary(self):
        self.assertEqual(estimar_fecha("17/10/2026"), "21-10-2026")
        # No se han configurado feriados, por lo que 1 de enero cuenta como hábil.
        self.assertEqual(estimar_fecha("2026-12-30"), "04-01-2027")

    def test_invalid_or_missing_date_is_not_invented(self):
        for value in (None, "", "Ok", "31/02/2026", 7502):
            with self.subTest(value=value):
                self.assertEqual(estimar_fecha(value), "")

    def test_literal_t_wins_over_other_previsto_columns(self):
        headers = ["NV", "Estado Logistica", "Produccion"] + [f"col{i}" for i in range(16)] + ["Previsto", "Previsto"]
        row = ["7511", "", "Corte"] + [None] * 16 + [date(2026, 10, 16), date(2030, 1, 1)]
        r = lookup_rockers_order(headers, [row], "7511")
        self.assertEqual(r["fecha_aproximada"], "21-10-2026")

    def test_missing_t_header_fails_in_adapters(self):
        with self.assertRaises(ValueError):
            cabeceras_con_previsto(["NV", "Previsto"])

    def test_blank_t_does_not_fall_back_to_reprogrammed_dates(self):
        headers = ["NV", "Estado Logistica", COLUMNA_PREVISTO, "3era Fecha Reprogramada"]
        r = lookup_rockers_order(headers, [["7511", "", "", "30-10-2026"]], "7511")
        self.assertEqual(r["fecha_aproximada"], "Pendiente de confirmar")

    def test_different_t_dates_require_review(self):
        headers = ["NV", "Estado Logistica", COLUMNA_PREVISTO]
        rows = [["7511", "", "16-10-2026"], ["7511", "", "20-10-2026"]]
        self.assertEqual(lookup_rockers_order(headers, rows, "7511"), {"resultado": "requiere_revision"})

    def test_three_business_day_threshold_and_overdue(self):
        today = date(2026, 10, 16)  # viernes -> umbral miércoles
        self.assertTrue(requiere_aviso("15-10-2026", today))
        self.assertTrue(requiere_aviso("16-10-2026", today))
        self.assertTrue(requiere_aviso("21-10-2026", today))
        self.assertFalse(requiere_aviso("22-10-2026", today))
        self.assertFalse(requiere_aviso("Pendiente de confirmar", today))

    def test_delay_message_only_for_orders_still_in_manufacturing(self):
        for estado in (ESTADO_PRODUCCION, ESTADO_RECEPCIONADO, ESTADO_STOCK_FABRICA):
            with self.subTest(estado=estado):
                answer = redactar({"numero_pedido": "7511", "estado": estado, "fecha_aproximada": "21-10-2026"}, hoy=date(2026, 10, 16))
                self.assertIn("Estamos atrasados con la fabricación", answer)
                self.assertIn("este rango podría cambiar", answer)
                self.assertNotIn("archivo", answer.lower())

    def test_past_estimate_is_not_promised_as_a_future_delivery(self):
        answer = redactar({"numero_pedido": "7511", "estado": ESTADO_PRODUCCION, "fecha_aproximada": "15-10-2026"}, hoy=date(2026, 10, 23))
        self.assertIn("La entrega estaba estimada", answer)
        self.assertIn("ponernos al día", answer)
        self.assertNotIn("estimamos la entrega para", answer)

    def test_no_delay_notice_for_dispatch_delivered_cancelled_or_contact(self):
        for estado in ("ENTREGADO", "CANCELADO", "EN RUTA", "COORDINACION", ESTADO_CONTACTO):
            with self.subTest(estado=estado):
                answer = redactar({"numero_pedido": "7511", "estado": estado, "fecha_aproximada": "15-10-2026"}, hoy=date(2026, 10, 16))
                self.assertNotIn("atrasados", answer)
                if estado in ("ENTREGADO", "CANCELADO"):
                    self.assertNotIn("fecha", answer.lower())

    def test_future_estimate_uses_natural_spanish_date(self):
        answer = redactar({"numero_pedido": "7511", "estado": ESTADO_PRODUCCION, "fecha_aproximada": "30-10-2026"}, hoy=date(2026, 10, 16))
        self.assertIn("entre el 30 de octubre y el 5 de noviembre de 2026", answer)
        self.assertNotIn("atrasados", answer)

    def test_past_date_in_warehouse_requires_updated_date_without_manufacturing_claim(self):
        answer = redactar({"numero_pedido": "7502", "estado": ESTADO_CONTACTO, "fecha_aproximada": "12-10-2026"}, hoy=date(2026, 10, 20))
        self.assertIn("debe confirmar un rango actualizado", answer)
        self.assertNotIn("estimamos la entrega para", answer)
        self.assertNotIn("atrasados con la fabricación", answer)


if __name__ == "__main__":
    unittest.main()
