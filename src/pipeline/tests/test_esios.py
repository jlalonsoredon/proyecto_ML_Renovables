"""Contrato de la previsión eólica de REE en ESIOS (spec 004, RF-3; T-12).

Sin red: la respuesta de la API entra como parámetro. Lo que se protege es que
el día natural no se desplace por la zona horaria, que el sello de elaboración
se archive tal cual y que una respuesta incompleta sea una incidencia legible y
no una fila inventada (CA-3.2, CA-3.3, CA-1.4).
"""

import sys
import unittest
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "src" / "pipeline"))

import esios  # noqa: E402
import prevision  # noqa: E402

ELABORADO = "2026-11-07T10:50:22.000+01:00"


def valor(dia="2026-11-08", energia=204233.8, geo=esios.GEO_PENINSULA):
    """Valor diario tal y como lo publica ESIOS (hora local y UTC)."""
    return {
        "value": energia,
        "datetime": f"{dia}T00:00:00.000+01:00",
        "datetime_utc": f"{dia}T00:00:00.000Z",
        "tz_time": f"{dia}T00:00:00.000Z",
        "geo_id": geo,
        "geo_name": "Península",
    }


def payload(valores, elaborado=ELABORADO):
    indicador = {
        "name": "Previsión diaria D+1 eólica",
        "id": esios.INDICADOR_PREVISION_EOLICA,
        "geos": [{"geo_id": esios.GEO_PENINSULA, "geo_name": "Península"}],
        "values": valores,
    }
    if elaborado is not None:
        indicador["values_updated_at"] = elaborado
    return {"indicator": indicador}


class TestPeticion(unittest.TestCase):
    def test_la_url_apunta_al_indicador_1777(self):
        self.assertEqual(
            esios.url_indicador(),
            "https://api.esios.ree.es/indicators/1777",
        )

    def test_los_parametros_piden_un_solo_dia_peninsular(self):
        parametros = esios.parametros_dia(date(2026, 11, 8))
        self.assertEqual(parametros["start_date"], "2026-11-08T00:00")
        self.assertEqual(parametros["end_date"], "2026-11-08T23:59")
        self.assertEqual(parametros["time_trunc"], "day")
        self.assertEqual(parametros["geo_ids[]"], 8741)


class TestFilasPrevision(unittest.TestCase):
    def test_una_respuesta_de_un_dia_da_una_fila_del_archivo(self):
        filas, motivos = esios.filas_prevision(
            payload([valor()]), date(2026, 11, 8))
        self.assertEqual(len(filas), 1)
        self.assertEqual(motivos, [])
        fila = filas[0]
        self.assertEqual(fila["objetivo"], date(2026, 11, 8))
        self.assertEqual(fila["ubicacion"], "peninsula")
        self.assertEqual(fila["uso"], "eolica")
        self.assertEqual(fila["eolica_mwh"], 204233.8)
        self.assertEqual(fila["elaborado"], ELABORADO)

    def test_la_fila_tiene_las_claves_de_la_capa_de_persistencia(self):
        filas, _ = esios.filas_prevision(payload([valor()]), date(2026, 11, 8))
        exigidas = {"fuente", "elaborado", "objetivo", "ubicacion", "uso",
                    "eolica_mwh", "parte_json"}
        # `fuente` la añade `save_forecast_rows`; el resto debe venir de aquí.
        self.assertEqual(exigidas - {"fuente"} - set(filas[0]), set())

    def test_el_dia_no_se_desplaza_por_la_zona_horaria(self):
        # 00:00 del día 8 en la Península son las 23:00 UTC del día 7: el día
        # natural sale de `datetime`, nunca de `datetime_utc`.
        filas, _ = esios.filas_prevision(payload([valor()]))
        self.assertEqual([fila["objetivo"] for fila in filas],
                         [date(2026, 11, 8)])

    def test_el_objetivo_filtra_los_demas_dias_sin_contarlos_como_fallo(self):
        dias = [valor("2026-11-07", 61829.9), valor("2026-11-08", 204233.8)]
        filas, motivos = esios.filas_prevision(payload(dias), date(2026, 11, 8))
        self.assertEqual([fila["eolica_mwh"] for fila in filas], [204233.8])
        self.assertEqual(motivos, [])

    def test_sin_objetivo_se_archivan_todos_los_dias(self):
        dias = [valor("2026-11-07", 61829.9), valor("2026-11-08", 204233.8)]
        filas, _ = esios.filas_prevision(payload(dias))
        self.assertEqual([fila["objetivo"] for fila in filas],
                         [date(2026, 11, 7), date(2026, 11, 8)])

    def test_una_respuesta_sin_el_dia_pedido_es_un_motivo(self):
        filas, motivos = esios.filas_prevision(
            payload([valor("2026-11-07")]), date(2026, 11, 8))
        self.assertEqual(filas, [])
        self.assertEqual(len(motivos), 1)
        self.assertIn("2026-11-08", motivos[0])

    def test_un_valor_sin_energia_no_es_una_fila(self):
        filas, motivos = esios.filas_prevision(
            payload([valor(energia=None)]), date(2026, 11, 8))
        self.assertEqual(filas, [])
        self.assertIn("sin energía", motivos[0])

    def test_un_nan_no_es_energia(self):
        filas, motivos = esios.filas_prevision(
            payload([valor(energia=float("nan"))]), date(2026, 11, 8))
        self.assertEqual(filas, [])
        self.assertIn("sin energía", motivos[0])

    def test_sin_elaboracion_la_fila_se_guarda_pero_no_es_elegible(self):
        filas, _ = esios.filas_prevision(
            payload([valor()], elaborado=None), date(2026, 11, 8))
        self.assertEqual(filas[0]["elaborado"], "")

    def test_un_ambito_que_no_es_la_peninsula_se_descarta(self):
        filas, motivos = esios.filas_prevision(
            payload([valor(geo=8742)]), date(2026, 11, 8))
        self.assertEqual(filas, [])
        self.assertIn("fuera de la Península", motivos[0])

    def test_un_valor_duplicado_deja_el_ultimo_y_lo_avisa(self):
        dias = [valor(energia=1.0), valor(energia=2.0)]
        filas, motivos = esios.filas_prevision(payload(dias), date(2026, 11, 8))
        self.assertEqual(filas[0]["eolica_mwh"], 2.0)
        self.assertIn("duplicado", motivos[0])

    def test_un_valor_que_no_es_objeto_es_un_motivo(self):
        filas, motivos = esios.filas_prevision(
            payload(["204233.8"]), date(2026, 11, 8))
        self.assertEqual(filas, [])
        self.assertTrue(motivos)


class TestRespuestaMala(unittest.TestCase):
    def test_una_respuesta_que_no_es_objeto_falla(self):
        with self.assertRaises(esios.RespuestaInesperada):
            esios.filas_prevision(["no es un diccionario"])

    def test_sin_indicator_falla(self):
        with self.assertRaises(esios.RespuestaInesperada):
            esios.filas_prevision({"data": {}})

    def test_sin_values_falla(self):
        with self.assertRaises(esios.RespuestaInesperada):
            esios.filas_prevision({"indicator": {"id": 1777}})

    def test_values_que_no_es_lista_falla(self):
        with self.assertRaises(esios.RespuestaInesperada):
            esios.filas_prevision({"indicator": {"values": {}}})


class TestReconstruido(unittest.TestCase):
    """Relleno histórico: etiqueta derivada y parte reducido (T-12.3b)."""

    def test_el_elaborado_es_el_dia_anterior_al_objetivo(self):
        filas, _ = esios.filas_prevision(
            payload([valor("2026-03-14")]), reconstruido=True)
        self.assertEqual(filas[0]["elaborado"], "2026-03-13")

    def test_el_parte_se_reduce_al_valor_y_su_procedencia(self):
        filas, _ = esios.filas_prevision(
            payload([valor("2026-03-14", 123456.7)]), reconstruido=True)
        parte = filas[0]["parte_json"]
        self.assertTrue(parte["reconstruido"])
        self.assertEqual(parte["regla"], "objetivo-1")
        self.assertEqual(parte["sello_ventana"], ELABORADO)
        self.assertEqual(parte["ventana"], ["2026-03-14", "2026-03-14"])
        self.assertEqual(parte["valor"]["value"], 123456.7)

    def test_no_guarda_la_respuesta_completa_en_cada_fila(self):
        filas, _ = esios.filas_prevision(
            payload([valor("2026-03-14")]), reconstruido=True)
        self.assertNotIn("indicator", filas[0]["parte_json"])

    def test_la_ventana_cubre_todos_los_dias_de_la_respuesta(self):
        dias = [valor("2022-01-01"), valor("2022-06-15"), valor("2022-12-31")]
        filas, _ = esios.filas_prevision(payload(dias), reconstruido=True)
        self.assertEqual(filas[0]["parte_json"]["ventana"],
                         ["2022-01-01", "2022-12-31"])
        self.assertEqual(filas[-1]["elaborado"], "2022-12-30")


class TestBloqueVerificable(unittest.TestCase):
    def test_un_bloque_con_sello_del_dia_anterior_es_fiable(self):
        indicador = payload(
            [valor("2022-12-31")],
            elaborado="2022-12-30T10:50:46.000+01:00",
        )["indicator"]
        self.assertEqual(
            esios.bloque_verificable(indicador, date(2022, 12, 31)), (True, ""))

    def test_un_sello_posterior_descarta_el_bloque(self):
        indicador = payload(
            [valor("2019-01-05")],
            elaborado="2019-12-26T15:59:51.000+01:00",
        )["indicator"]
        verificable, motivo = esios.bloque_verificable(
            indicador, date(2019, 1, 5))
        self.assertFalse(verificable)
        self.assertIn("revisarse después", motivo)

    def test_sin_sello_no_hay_bloque_fiable(self):
        indicador = payload([valor()], elaborado=None)["indicator"]
        verificable, motivo = esios.bloque_verificable(
            indicador, date(2026, 11, 8))
        self.assertFalse(verificable)
        self.assertIn("values_updated_at", motivo)

    def test_sin_valores_no_hay_bloque_fiable(self):
        indicador = payload([])["indicator"]
        indicador["values_updated_at"] = ELABORADO
        verificable, motivo = esios.bloque_verificable(
            indicador, date(2026, 11, 8))
        self.assertFalse(verificable)
        self.assertIn("ningún día", motivo)

    def test_el_fin_del_bloque_manda(self):
        # El sello es el 2026-11-07 y la respuesta trae ese mismo día.
        indicador = payload([valor("2026-11-07")])["indicator"]
        # Con ese día como final, el sello esperado sería el 6: no cuadra.
        self.assertFalse(
            esios.bloque_verificable(indicador, date(2026, 11, 7))[0])
        # Con el final en mañana, el sello es justo el día anterior.
        self.assertTrue(
            esios.bloque_verificable(indicador, date(2026, 11, 8))[0])


class TestVentanaSolicitada(unittest.TestCase):
    def test_el_dia_extra_de_esios_no_se_archiva(self):
        dias = [valor("2022-01-01"), valor("2022-12-31"), valor("2023-01-01")]
        filas, _ = esios.filas_prevision(
            payload(dias), reconstruido=True,
            ventana_solicitada=(date(2022, 1, 1), date(2022, 12, 31)))
        self.assertEqual([fila["objetivo"] for fila in filas],
                         [date(2022, 1, 1), date(2022, 12, 31)])

    def test_la_ventana_del_parte_es_la_pedida(self):
        dias = [valor("2022-01-01"), valor("2022-12-31"), valor("2023-01-01")]
        filas, _ = esios.filas_prevision(
            payload(dias), reconstruido=True,
            ventana_solicitada=(date(2022, 1, 1), date(2022, 12, 31)))
        self.assertEqual(filas[0]["parte_json"]["ventana"],
                         ["2022-01-01", "2022-12-31"])


class TestHuecos(unittest.TestCase):
    def test_un_rango_completo_no_tiene_huecos(self):
        filas = [{"objetivo": date(2022, 1, 1)},
                 {"objetivo": date(2022, 1, 2)}]
        self.assertEqual(
            esios.huecos(filas, date(2022, 1, 1), date(2022, 1, 2)), [])

    def test_un_dia_sin_fila_se_declara(self):
        filas = [{"objetivo": date(2022, 1, 1)},
                 {"objetivo": date(2022, 1, 3)}]
        self.assertEqual(
            esios.huecos(filas, date(2022, 1, 1), date(2022, 1, 3)),
            [date(2022, 1, 2)])

    def test_acepta_fechas_sueltas(self):
        self.assertEqual(
            esios.huecos([date(2022, 1, 2)], date(2022, 1, 1), date(2022, 1, 2)),
            [date(2022, 1, 1)])


class TestParametrosRango(unittest.TestCase):
    def test_el_rango_pide_los_dos_extremos_peninsulares(self):
        parametros = esios.parametros_rango("2022-01-01", date(2022, 12, 31))
        self.assertEqual(parametros["start_date"], "2022-01-01T00:00")
        self.assertEqual(parametros["end_date"], "2022-12-31T23:59")
        self.assertEqual(parametros["time_trunc"], "day")
        self.assertEqual(parametros["geo_ids[]"], 8741)


class TestElaboracion(unittest.TestCase):
    def test_el_instante_acepta_texto_iso_con_zona(self):
        self.assertEqual(
            prevision.instante_elaboracion(ELABORADO),
            datetime(2026, 11, 7, 10, 50, 22),
        )

    def test_el_instante_acepta_datetime_y_date(self):
        self.assertEqual(
            prevision.instante_elaboracion(datetime(2026, 11, 7, 10, 50)),
            datetime(2026, 11, 7, 10, 50),
        )
        self.assertEqual(
            prevision.instante_elaboracion(date(2026, 11, 7)),
            datetime(2026, 11, 7),
        )

    def test_un_texto_vacio_o_ilegible_no_tiene_instante(self):
        self.assertIsNone(prevision.instante_elaboracion(""))
        self.assertIsNone(prevision.instante_elaboracion(None))
        self.assertIsNone(prevision.instante_elaboracion("ayer"))


if __name__ == "__main__":
    unittest.main()
