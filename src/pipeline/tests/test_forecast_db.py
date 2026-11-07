"""Contrato del archivo de previsiones en el backend (spec 003, RF-2, RF-4, RF-13).

Sin red: se usa una base SQLite en memoria. La puerta es `node --test`
(gate.test.mjs), que descubre esta suite junto con la del pipeline.
"""

import json
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "src" / "pipeline"))
sys.path.insert(0, str(RAIZ / "backend"))

import forecast  # noqa: E402
from app.services import forecast_db  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def parte(nombre: str) -> dict:
    return json.loads((FIXTURES / f"prediccion_{nombre}.json").read_text(encoding="utf-8"))


def filas_reales(ubicacion="Gecama (Cuenca)", uso="eolica", lat=39.4085):
    """Las siete filas que salen de los partes reales de los fixtures."""
    diario = forecast.parse_daily_parte(parte("diaria"))
    horario = forecast.parse_hourly_parte(parte("horaria"))
    return forecast.forecast_rows(
        diario, horario, ubicacion, uso, lat, datetime(2026, 11, 2, 15, 50),
    )


class BaseArchivo(unittest.TestCase):
    def setUp(self):
        self.conn = forecast_db.connect(":memory:")
        forecast_db.ensure_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def filas(self):
        return self.conn.execute(
            "SELECT elaborado, objetivo, ubicacion, viento_ms FROM prediccion_aemet "
            "ORDER BY objetivo, ubicacion"
        ).fetchall()


class TestEsquema(BaseArchivo):
    def test_crear_el_esquema_dos_veces_no_falla(self):
        forecast_db.ensure_schema(self.conn)
        tablas = {
            fila[0] for fila in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertIn("prediccion_aemet", tablas)
        self.assertIn("captura_estado", tablas)

    def test_el_archivo_no_toca_la_tabla_de_observacion(self):
        tablas = {
            fila[0] for fila in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertNotIn("aemet_diario", tablas)

    def test_la_clave_es_elaboracion_objetivo_y_ubicacion(self):
        claves = [
            fila[1] for fila in self.conn.execute("PRAGMA table_info(prediccion_aemet)")
        ]
        clave = [
            fila[1] for fila in sorted(
                self.conn.execute("PRAGMA table_info(prediccion_aemet)"),
                key=lambda fila: fila[5],
            )
            if fila[5] > 0
        ]
        self.assertEqual(clave, ["elaborado", "objetivo", "ubicacion"])
        self.assertIn("capturado_en", claves)


class TestIdempotencia(BaseArchivo):
    def test_una_captura_guarda_los_siete_dias(self):
        guardadas = forecast_db.save_forecast(self.conn, filas_reales(), parte("diaria"))
        self.assertEqual(guardadas, 7)
        self.assertEqual(len(self.filas()), 7)

    def test_recapturar_la_misma_elaboracion_no_duplica(self):
        filas = filas_reales()
        forecast_db.save_forecast(self.conn, filas, parte("diaria"))
        forecast_db.save_forecast(self.conn, filas, parte("diaria"))
        self.assertEqual(len(self.filas()), 7)

    def test_recapturar_la_misma_elaboracion_sustituye_el_valor(self):
        filas = filas_reales()
        forecast_db.save_forecast(self.conn, filas, parte("diaria"))
        corregidas = [dict(fila, viento_ms=1.234) for fila in filas]
        forecast_db.save_forecast(self.conn, corregidas, parte("diaria"))

        self.assertEqual(len(self.filas()), 7)
        self.assertTrue(all(fila[3] == 1.234 for fila in self.filas()))

    def test_una_elaboracion_nueva_se_anade_y_conserva_la_anterior(self):
        forecast_db.save_forecast(self.conn, filas_reales(), parte("diaria"))
        nueva = [
            dict(fila, elaborado=datetime(2026, 11, 3, 8, 59))
            for fila in filas_reales()
        ]
        forecast_db.save_forecast(self.conn, nueva, parte("diaria"))

        self.assertEqual(len(self.filas()), 14)
        objetivos = {fila[1] for fila in self.filas()}
        self.assertEqual(len(objetivos), 7)

    def test_una_elaboracion_nueva_no_pisa_otro_dia_objetivo(self):
        forecast_db.save_forecast(self.conn, filas_reales(), parte("diaria"))
        una = [
            dict(fila, elaborado=datetime(2026, 11, 3, 8, 59))
            for fila in filas_reales()[:1]
        ]
        forecast_db.save_forecast(self.conn, una, parte("diaria"))
        self.assertEqual(len(self.filas()), 8)

    def test_un_parte_sin_elaboracion_se_guarda_marcado(self):
        sin = [dict(fila, elaborado=None) for fila in filas_reales()[:2]]
        guardadas = forecast_db.save_forecast(self.conn, sin, parte("diaria"))
        self.assertEqual(guardadas, 2)

        elaborados = {fila[0] for fila in self.filas()}
        self.assertEqual(elaborados, {""})

    def test_los_valores_ausentes_siguen_siendo_ausentes(self):
        filas = [dict(fila, racha_ms=None, sol=None) for fila in filas_reales()[:1]]
        forecast_db.save_forecast(self.conn, filas, parte("diaria"))
        racha, sol = self.conn.execute(
            "SELECT racha_ms, sol FROM prediccion_aemet"
        ).fetchone()
        self.assertIsNone(racha)
        self.assertIsNone(sol)

    def test_el_parte_original_queda_guardado(self):
        forecast_db.save_forecast(self.conn, filas_reales()[:1], parte("diaria"))
        original = self.conn.execute(
            "SELECT parte_json FROM prediccion_aemet"
        ).fetchone()[0]
        self.assertEqual(json.loads(original)["elaborado"], "2026-11-02T15:45:08")


class TestLecturas(BaseArchivo):
    def test_dias_archivados_devuelve_los_objetivos(self):
        forecast_db.save_forecast(self.conn, filas_reales(), parte("diaria"))
        self.assertEqual(
            forecast_db.archived_days(self.conn),
            {date(2026, 11, 2) + timedelta(days=desplazamiento) for desplazamiento in range(7)},
        )

    def test_archivo_vacio_no_tiene_dias(self):
        self.assertEqual(forecast_db.archived_days(self.conn), set())

    def test_las_filas_se_pueden_leer_por_rango(self):
        forecast_db.save_forecast(self.conn, filas_reales(), parte("diaria"))
        leidas = forecast_db.rows_between(
            self.conn, date(2026, 11, 3), date(2026, 11, 4),
        )
        self.assertEqual(len(leidas), 2)
        self.assertEqual({fila["objetivo"] for fila in leidas},
                         {date(2026, 11, 3), date(2026, 11, 4)})

    def test_la_fila_leida_conserva_su_tipo_de_fecha(self):
        forecast_db.save_forecast(self.conn, filas_reales()[:1], parte("diaria"))
        fila = forecast_db.rows_between(
            self.conn, date(2026, 11, 2), date(2026, 11, 2),
        )[0]
        self.assertIsInstance(fila["objetivo"], date)
        self.assertIsInstance(fila["elaborado"], datetime)


class TestEstadoCaptura(BaseArchivo):
    def test_cada_ejecucion_deja_su_resumen(self):
        forecast_db.register_capture(
            self.conn,
            ejecutada_en=datetime(2026, 11, 2, 3, 0),
            ubicaciones_ok=12,
            ubicaciones_error=0,
            filas_guardadas=84,
            estado="ok",
            detalle="horizonte de 7 días",
        )
        resumen = forecast_db.last_capture(self.conn)
        self.assertEqual(resumen["ubicaciones_ok"], 12)
        self.assertEqual(resumen["filas_guardadas"], 84)
        self.assertEqual(resumen["estado"], "ok")
        self.assertEqual(resumen["detalle"], "horizonte de 7 días")

    def test_sin_capturas_no_hay_resumen(self):
        self.assertIsNone(forecast_db.last_capture(self.conn))

    def test_la_ultima_captura_es_la_mas_reciente(self):
        for hora, estado in ((3, "ok"), (4, "parcial")):
            forecast_db.register_capture(
                self.conn,
                ejecutada_en=datetime(2026, 11, 2, hora, 0),
                ubicaciones_ok=12 - hora,
                ubicaciones_error=hora - 3,
                filas_guardadas=10,
                estado=estado,
                detalle="",
            )
        self.assertEqual(forecast_db.last_capture(self.conn)["estado"], "parcial")

    def test_una_captura_sin_ubicaciones_queda_en_fallo(self):
        forecast_db.register_capture(
            self.conn,
            ejecutada_en=datetime(2026, 11, 2, 3, 0),
            ubicaciones_ok=0,
            ubicaciones_error=12,
            filas_guardadas=0,
            estado="fallo",
            detalle="HTTP 429 en las 12 ubicaciones",
        )
        self.assertTrue(forecast_db.capture_failed(forecast_db.last_capture(self.conn)))


if __name__ == "__main__":
    unittest.main()
