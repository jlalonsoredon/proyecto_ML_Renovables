"""Contrato del cliente y de la captura de previsiones (spec 003, RF-1 a RF-6, RF-13).

Sin red: se sustituye la sesión HTTP y el descargador. La puerta es `node --test`.
"""

import json
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "src" / "pipeline"))
sys.path.insert(0, str(RAIZ / "backend"))

from app.services import aemet_forecast, forecast_db  # noqa: E402
from app.services.forecast_logic import UBICACIONES  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
HOY = date(2026, 11, 2)


def parte(nombre: str) -> dict:
    return json.loads((FIXTURES / f"prediccion_{nombre}.json").read_text(encoding="utf-8"))


class RespuestaFalsa:
    def __init__(self, status_code=200, datos=None):
        self.status_code = status_code
        self._datos = datos

    def json(self):
        if isinstance(self._datos, Exception):
            raise self._datos
        return self._datos


class SesionFalsa:
    """Devuelve las respuestas en orden y anota las URLs pedidas."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.urls = []

    def get(self, url, params=None, timeout=None):
        self.urls.append(url)
        respuesta = self.respuestas.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


class BaseSinEsperas(unittest.TestCase):
    def setUp(self):
        self._dormir = aemet_forecast.time.sleep
        aemet_forecast.time.sleep = lambda segundos: None

    def tearDown(self):
        aemet_forecast.time.sleep = self._dormir


class TestDescarga(BaseSinEsperas):
    def test_la_descarga_usa_los_dos_pasos(self):
        sesion = SesionFalsa([
            RespuestaFalsa(200, {"datos": "https://opendata.aemet.es/datos/abc"}),
            RespuestaFalsa(200, [parte("diaria")]),
        ])
        contenido, error = aemet_forecast.descargar_parte("16078", "diaria", "clave", sesion)

        self.assertIsNone(error)
        self.assertEqual(contenido["nombre"], "Cuenca")
        self.assertEqual(len(sesion.urls), 2)
        self.assertIn("municipio/diaria/16078", sesion.urls[0])
        self.assertEqual(sesion.urls[1], "https://opendata.aemet.es/datos/abc")

    def test_un_429_se_reintenta_y_no_se_pierde(self):
        sesion = SesionFalsa([
            RespuestaFalsa(429),
            RespuestaFalsa(200, {"datos": "https://opendata.aemet.es/datos/abc"}),
            RespuestaFalsa(200, [parte("horaria")]),
        ])
        contenido, error = aemet_forecast.descargar_parte("16078", "horaria", "clave", sesion)
        self.assertIsNone(error)
        self.assertIsNotNone(contenido)

    def test_el_parte_sin_url_de_datos_explica_el_motivo(self):
        sesion = SesionFalsa([RespuestaFalsa(200, {"descripcion": "No hay datos"})])
        contenido, error = aemet_forecast.descargar_parte("16078", "diaria", "clave", sesion)
        self.assertIsNone(contenido)
        self.assertEqual(error, "No hay datos")

    def test_un_http_distinto_de_200_es_un_error_con_su_codigo(self):
        sesion = SesionFalsa([RespuestaFalsa(404)])
        contenido, error = aemet_forecast.descargar_parte("16078", "diaria", "clave", sesion)
        self.assertIsNone(contenido)
        self.assertEqual(error, "HTTP 404")

    def test_un_timeout_agotado_no_lanza(self):
        from requests.exceptions import Timeout
        sesion = SesionFalsa([Timeout(), Timeout()])
        contenido, error = aemet_forecast.descargar_parte("16078", "diaria", "clave", sesion)
        self.assertIsNone(contenido)
        self.assertEqual(error, "timeout")

    def test_un_fallo_de_red_no_lanza(self):
        from requests.exceptions import ConnectionError as ErrorDeRed
        sesion = SesionFalsa([ErrorDeRed("sin ruta al host")])
        contenido, error = aemet_forecast.descargar_parte("16078", "diaria", "clave", sesion)
        self.assertIsNone(contenido)
        self.assertTrue(error.startswith("red:"))


class RelojFalso:
    """Reloj controlado: fecha cada ejecución en el `hoy` simulado.

    Sin esto, `capturado_en` usa la fecha real y una captura simulada en el
    pasado queda registrada como posterior a `hoy`, de modo que el archivo no
    exige ningún día pendiente y el resumen miente (CA-6.6).
    """

    hoy = HOY

    @classmethod
    def now(cls):
        return datetime.combine(cls.hoy, datetime.min.time()).replace(hour=12)


class BaseCaptura(unittest.TestCase):
    def setUp(self):
        self._dormir = aemet_forecast.time.sleep
        aemet_forecast.time.sleep = lambda segundos: None
        self._reloj = aemet_forecast.datetime
        aemet_forecast.datetime = RelojFalso
        self.conn = forecast_db.connect(":memory:")
        forecast_db.ensure_schema(self.conn)

    def tearDown(self):
        aemet_forecast.time.sleep = self._dormir
        aemet_forecast.datetime = self._reloj
        self.conn.close()

    @staticmethod
    def descargador_ok(ubicacion):
        return {
            "diaria": parte("diaria"),
            "horaria": parte("horaria"),
            "errores": [],
        }

    def capturar(self, **cambios):
        argumentos = {
            "hoy": HOY,
            "descargador": self.descargador_ok,
            "conn": self.conn,
        }
        argumentos.update(cambios)
        RelojFalso.hoy = argumentos["hoy"]
        return aemet_forecast.capture_forecast(**argumentos)


class TestCaptura(BaseCaptura):
    def test_guarda_una_fila_por_dia_y_ubicacion(self):
        resumen = self.capturar()

        self.assertEqual(resumen["ubicaciones_ok"], 12)
        self.assertEqual(resumen["filas_guardadas"], 84)
        self.assertEqual(resumen["estado"], "ok")
        self.assertEqual(len(forecast_db.archived_days(self.conn)), 7)

    def test_el_resumen_declara_el_horizonte_y_los_errores(self):
        resumen = self.capturar()

        self.assertEqual(resumen["horizonte_dias"], 7)
        self.assertEqual(resumen["errores"], [])
        self.assertEqual(resumen["dias_sin_capturar"], [])
        self.assertIn("12 ubicaciones capturadas", resumen["detalle"])

    def test_cada_ubicacion_conserva_su_uso(self):
        self.capturar()
        usos = {
            fila[0] for fila in self.conn.execute(
                "SELECT DISTINCT uso FROM prediccion_aemet"
            )
        }
        self.assertEqual(usos, {"eolica", "solar"})

    def test_una_captura_repetida_no_duplica(self):
        self.capturar()
        self.capturar()
        filas = self.conn.execute("SELECT COUNT(*) FROM prediccion_aemet").fetchone()[0]
        self.assertEqual(filas, 84)

    def test_una_elaboracion_nueva_de_un_dia_ya_cubierto_se_guarda(self):
        self.capturar()

        def descargador(ubicacion):
            diaria = json.loads(json.dumps(parte("diaria")))
            diaria["elaborado"] = "2026-11-02T21:10:00"
            return {"diaria": diaria, "horaria": None, "errores": []}

        self.capturar(descargador=descargador)
        filas = self.conn.execute("SELECT COUNT(*) FROM prediccion_aemet").fetchone()[0]
        self.assertEqual(filas, 168)
        elaboraciones = {
            fila[0] for fila in self.conn.execute(
                "SELECT DISTINCT elaborado FROM prediccion_aemet WHERE objetivo = ?",
                (HOY.isoformat(),),
            )
        }
        self.assertEqual(elaboraciones, {"2026-11-02T15:45:08", "2026-11-02T21:10:00"})

    def test_un_dia_fuera_del_horizonte_no_se_archiva(self):
        def descargador(ubicacion):
            diaria = json.loads(json.dumps(parte("diaria")))
            diaria["elaborado"] = "2026-10-01T08:00:00"
            for dia in diaria["prediccion"]["dia"]:
                dia["fecha"] = dia["fecha"].replace("2026-11-", "2026-10-")
            return {"diaria": diaria, "horaria": None, "errores": []}

        resumen = self.capturar(descargador=descargador)

        self.assertEqual(resumen["filas_guardadas"], 0)
        self.assertEqual(forecast_db.archived_days(self.conn), set())

    def test_el_resumen_registra_la_elaboracion_servida(self):
        resumen = self.capturar()
        self.assertEqual(resumen["elaboraciones"], ["2026-11-02T15:45:08"])
        self.assertIn("elaboración 2026-11-02T15:45:08", resumen["detalle"])

    def test_una_ejecucion_deja_su_fila_de_estado(self):
        self.capturar()
        estado = forecast_db.last_capture(self.conn)
        self.assertEqual(estado["ubicaciones_ok"], 12)
        self.assertEqual(estado["filas_guardadas"], 84)
        self.assertEqual(estado["estado"], "ok")
        self.assertFalse(forecast_db.capture_failed(estado))

    def test_un_fallo_parcial_no_detiene_el_resto(self):
        falla = UBICACIONES[0]["clave"]

        def descargador(ubicacion):
            if ubicacion["clave"] == falla:
                raise RuntimeError("sin respuesta")
            return self.descargador_ok(ubicacion)

        resumen = self.capturar(descargador=descargador)

        self.assertEqual(resumen["estado"], "parcial")
        self.assertEqual(resumen["ubicaciones_ok"], 11)
        self.assertEqual(resumen["ubicaciones_error"], 1)
        self.assertTrue(any(falla in error for error in resumen["errores"]))

    def test_una_ubicacion_sin_parte_diario_es_una_incidencia(self):
        sin_diario = UBICACIONES[0]["clave"]

        def descargador(ubicacion):
            partes = self.descargador_ok(ubicacion)
            if ubicacion["clave"] == sin_diario:
                partes = {"diaria": None, "horaria": parte("horaria"),
                          "errores": ["diaria: HTTP 500"]}
            return partes

        resumen = self.capturar(descargador=descargador)

        self.assertEqual(resumen["ubicaciones_ok"], 11)
        self.assertEqual(resumen["estado"], "parcial")
        self.assertEqual(resumen["filas_guardadas"], 77)

    def test_sin_el_parte_horario_la_fila_sigue_valiendo(self):
        def descargador(ubicacion):
            return {"diaria": parte("diaria"), "horaria": None,
                    "errores": ["horaria: timeout"]}

        self.capturar(descargador=descargador)
        viento, racha, tmed = self.conn.execute(
            "SELECT viento_ms, racha_ms, tmed FROM prediccion_aemet LIMIT 1"
        ).fetchone()
        self.assertIsNotNone(viento)
        self.assertIsNotNone(tmed)
        self.assertIsNone(racha)   # sin el parte horario no hay racha

    def test_si_fallan_todas_la_captura_es_un_fallo_visible(self):
        def descargador(ubicacion):
            raise RuntimeError("AEMET caída")

        resumen = self.capturar(descargador=descargador)

        self.assertEqual(resumen["estado"], "fallo")
        self.assertEqual(resumen["filas_guardadas"], 0)
        self.assertEqual(len(resumen["errores"]), 12)
        self.assertTrue(forecast_db.capture_failed(resumen))

    def test_un_dia_sin_llegar_se_declara(self):
        def descargador(ubicacion):
            diaria = parte("diaria")
            # La fuente no devuelve el día en curso para nadie (CE-6).
            diaria = json.loads(json.dumps(diaria))
            diaria["prediccion"]["dia"] = diaria["prediccion"]["dia"][1:]
            return {"diaria": diaria, "horaria": None, "errores": []}

        resumen = self.capturar(descargador=descargador)

        self.assertIn(HOY, resumen["dias_sin_capturar"])
        self.assertEqual(resumen["horizonte_dias"], 6)

    def test_una_captura_posterior_cuenta_los_dias_pendientes(self):
        self.capturar()
        # El 9 de noviembre el archivo solo debería tener lo capturado hasta hoy.
        resumen = self.capturar(hoy=date(2026, 11, 9))

        self.assertGreater(resumen["dias_pendientes"], 0)
        self.assertIsNotNone(resumen["desde_pendiente"])
        self.assertTrue(resumen["desde_pendiente"] <= date(2026, 11, 9))


if __name__ == "__main__":
    unittest.main()
