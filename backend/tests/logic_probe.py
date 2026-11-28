"""Puente de test JSON → lógica Python real. No contiene reglas del dominio."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def _serializar(valor):
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {str(clave): _serializar(dato) for clave, dato in valor.items()}
    if isinstance(valor, (list, tuple, set)):
        return [_serializar(dato) for dato in valor]
    return valor


def _ejecutar(request):
    accion = request["action"]

    if accion == "create_legacy_db":
        ruta = request["db_path"]
        with sqlite3.connect(ruta) as conn:
            conn.execute(
                "CREATE TABLE legacy_sentinel (valor TEXT NOT NULL)"
            )
            conn.execute(
                "INSERT INTO legacy_sentinel (valor) VALUES ('solo_render')"
            )
            conn.execute(
                "CREATE TABLE predictions (fecha TEXT, prediccion_mwh REAL)"
            )
            conn.execute(
                "INSERT INTO predictions VALUES ('2026-01-01', 123.0)"
            )
        return {"created": True}

    if accion == "inspect_db":
        ruta = request["db_path"]
        with sqlite3.connect(ruta) as conn:
            tablas = {
                fila[0]
                for fila in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            conteos = {}
            for tabla in (
                "generacion", "aemet_diario", "prediccion_diaria",
                "prediccion_propia", "legacy_sentinel",
            ):
                if tabla in tablas:
                    conteos[tabla] = conn.execute(
                        f"SELECT COUNT(*) FROM {tabla}"
                    ).fetchone()[0]
        return {"tablas": sorted(tablas), "conteos": conteos}

    if accion == "model_contract":
        from app.services.model_loader import ModelService

        servicio = ModelService(
            model_path=request["model_path"],
            expected_features=request["expected_features"],
        )
        resultado = {
            "familia": servicio.family,
            "features": servicio.features,
            "usa_scaler": servicio.uses_scaler,
            "loaded": servicio.model is not None,
            "n_features_in": getattr(servicio.model, "n_features_in_", None),
        }
        if servicio.ready and request.get("reference_db"):
            from contextlib import closing

            source = Path(request["reference_db"]).resolve()
            uri = source.as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True)) as conn:
                row = conn.execute(
                    """SELECT vector_entrada, prediccion_mwh
                       FROM prediccion_propia
                       WHERE vector_entrada IS NOT NULL
                       ORDER BY fecha_objetivo DESC, fecha_emision DESC,
                                emitida_en DESC
                       LIMIT 1"""
                ).fetchone()
            if row is None:
                raise ValueError("la BD de referencia no contiene vector propio")
            vector = json.loads(row[0])
            ordered = {name: float(vector[name]) for name in servicio.features}
            prediction = servicio.predict_vector(ordered)
            resultado["inference"] = {
                "reference_mwh": float(row[1]),
                "backend_mwh": prediction,
                "abs_diff": abs(prediction - float(row[1])),
            }
        return resultado

    if accion == "resolve_window":
        from app.services.prediction_features import resolve_window

        return resolve_window(
            request["observaciones"],
            request["previsiones"],
            request["objetivo"],
            request["dias"],
            request["hoy"],
        )

    if accion == "freshness":
        from app.services.prediction_features import latest_complete_generation

        return latest_complete_generation(request["generacion"], request["hoy"])

    if accion == "missing_generation_dates":
        from app.services.ree_client import missing_generation_dates

        return [
            day.isoformat()
            for day in missing_generation_dates(
                request["presentes"], request["hoy"], request["dias"]
            )
        ]

    if accion == "ree_target":
        from app.services.prediction_features import resolve_eolica_prev

        return resolve_eolica_prev(
            request["previsiones_ree"], request["objetivo"], request["hoy"]
        )

    if accion == "national_series":
        from app.services.prediction_features import aemet_national_series

        return aemet_national_series(
            request["rows"], request["uso"], request["hoy"]
        )

    if accion == "build_map":
        from app.services.prediction_features import build_prediction_map

        return build_prediction_map(
            obs_meteo=request["obs_meteo"],
            obs_solar=request["obs_solar"],
            obs_gen=request["obs_gen"],
            aemet_rows=request["aemet_rows"],
            ree_rows=request["ree_rows"],
            hoy=request["hoy"],
        )

    if accion == "prediction_error":
        from app.services.prediction_features import prediction_error

        return prediction_error(
            request["fecha_objetivo"],
            request.get("real_mwh"),
            request["prediccion_mwh"],
            request["hoy"],
        )

    if accion == "aemet_capture_simulation":
        from app.services import aemet_client

        class Response:
            def __init__(self, status_code, payload):
                self.status_code = status_code
                self.payload = payload

            def json(self):
                return self.payload

        class Session:
            def __init__(self):
                self.calls = []
                self.first_station_attempts = 0

            def get(self, url, params=None, headers=None, timeout=None):
                self.calls.append({
                    "url": url,
                    "params": params,
                    "headers": headers,
                    "timeout": timeout,
                })
                if url.endswith("/estacion/4589X"):
                    self.first_station_attempts += 1
                    if self.first_station_attempts == 1:
                        return Response(429, {})
                    return Response(200, {"datos": "https://fixture.invalid/datos"})
                if url == "https://fixture.invalid/datos":
                    return Response(200, [{
                        "fecha": request["fecha"],
                        "indicativo": "4589X",
                        "tmed": "10,2",
                        "velmedia": "0",
                        "racha": "Ip",
                        "sol": "5",
                    }])
                return Response(503, {})

        original_key = aemet_client.AEMET_API_KEY
        session = Session()
        pausas = []
        aemet_client.AEMET_API_KEY = "fixture-aemet-key"
        try:
            rows = aemet_client.download_aemet_diario(
                request["fecha"],
                session=session,
                sleeper=pausas.append,
            )
        finally:
            aemet_client.AEMET_API_KEY = original_key
        return {
            "estaciones": aemet_client.ESTACIONES_OBSERVACION,
            "filas": rows,
            "reintento_429": 60 in pausas and session.first_station_attempts == 2,
            "dos_pasos": any(
                call["url"] == "https://fixture.invalid/datos"
                for call in session.calls
            ),
        }

    if accion == "aemet_forecast_capture":
        from app.services import aemet_forecast, db_ree
        from app.services.forecast_logic import UBICACIONES

        if not request.get("db_path"):
            raise ValueError("db_path es obligatorio para probar el archivo AEMET")
        os.environ["DB_PATH"] = request["db_path"]
        db_ree.DB_PATH = request["db_path"]
        db_ree.init_db()
        fixture_dir = (
            BACKEND_DIR.parent / "src" / "pipeline" / "tests" / "fixtures"
        )
        diaria_base = json.loads(
            (fixture_dir / "prediccion_diaria.json").read_text(encoding="utf-8")
        )
        horaria_base = json.loads(
            (fixture_dir / "prediccion_horaria.json").read_text(encoding="utf-8")
        )
        real_datetime = aemet_forecast.datetime
        real_sleep = aemet_forecast.time.sleep

        class Clock:
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 11, 2, 12, 0, tzinfo=tz)

        aemet_forecast.datetime = Clock
        aemet_forecast.time.sleep = lambda seconds: None

        def make_downloader(elaborado, falla_ubicacion=None):
            def descargar(ubicacion):
                if ubicacion["clave"] == falla_ubicacion:
                    raise RuntimeError("fallo parcial simulado")
                diaria = json.loads(json.dumps(diaria_base))
                horaria = json.loads(json.dumps(horaria_base))
                diaria["elaborado"] = elaborado
                horaria["elaborado"] = elaborado
                return {"diaria": diaria, "horaria": horaria, "errores": []}
            return descargar

        try:
            with db_ree._get_conn() as conn:
                primera = aemet_forecast.capture_forecast(
                    hoy=date(2026, 11, 2),
                    descargador=make_downloader("2026-11-02T15:45:08"),
                    conn=conn,
                    clave="fixture-aemet-key",
                )
                count_first = conn.execute(
                    "SELECT COUNT(*) FROM prediccion_diaria WHERE fuente='aemet'"
                ).fetchone()[0]
                aemet_forecast.capture_forecast(
                    hoy=date(2026, 11, 2),
                    descargador=make_downloader("2026-11-02T15:45:08"),
                    conn=conn,
                    clave="fixture-aemet-key",
                )
                count_same = conn.execute(
                    "SELECT COUNT(*) FROM prediccion_diaria WHERE fuente='aemet'"
                ).fetchone()[0]
                aemet_forecast.capture_forecast(
                    hoy=date(2026, 11, 2),
                    descargador=make_downloader("2026-11-02T21:10:00"),
                    conn=conn,
                    clave="fixture-aemet-key",
                )
                count_new = conn.execute(
                    "SELECT COUNT(*) FROM prediccion_diaria WHERE fuente='aemet'"
                ).fetchone()[0]
                parcial = aemet_forecast.capture_forecast(
                    hoy=date(2026, 11, 2),
                    descargador=make_downloader(
                        "2026-11-02T22:10:00",
                        falla_ubicacion=UBICACIONES[0]["clave"],
                    ),
                    conn=conn,
                    clave="fixture-aemet-key",
                )
                count_partial = conn.execute(
                    "SELECT COUNT(*) FROM prediccion_diaria WHERE fuente='aemet'"
                ).fetchone()[0]
        finally:
            aemet_forecast.datetime = real_datetime
            aemet_forecast.time.sleep = real_sleep
        return {
            "primera": {
                "estado": primera["estado"],
                "filas": count_first,
            },
            "tras_recaptura_igual": count_same,
            "tras_nueva_elaboracion": count_new,
            "parcial": {
                "estado": parcial["estado"],
                "ubicaciones_ok": parcial["ubicaciones_ok"],
            },
            "tras_parcial": count_partial,
        }

    if accion == "aemet_observation":
        from app.services.aemet_client import parse_daily_record

        return parse_daily_record(request["record"])

    if accion == "ree_d1":
        from app.services.ree_forecast_logic import parse_ree_d1

        return parse_ree_d1(
            request["payload"],
            request["objetivo"],
            request["hoy"],
            request["capturado_en"],
        )

    if accion == "ree_capture_simulation":
        from app.services import forecast_db, ree_forecast

        class Response:
            status_code = 200

            def json(self):
                return {
                    "indicator": {
                        "values_updated_at": "2026-01-10T08:00:00+01:00",
                        "values": [{
                            "datetime": "2026-01-11T00:00:00+01:00",
                            "datetime_utc": "2026-01-10T23:00:00Z",
                            "geo_id": 8741,
                            "value": 0,
                        }],
                    },
                }

        class Session:
            def __init__(self):
                self.request = None

            def get(self, url, params=None, headers=None, timeout=None):
                self.request = {
                    "url": url,
                    "params": params,
                    "headers": headers,
                    "timeout": timeout,
                }
                return Response()

        saved = {}
        session = Session()
        original_save = forecast_db.save_forecast_rows

        def capture_saved(conn, rows, fuente, parte=None):
            saved["rows"] = rows
            saved["fuente"] = fuente
            return len(rows)

        forecast_db.save_forecast_rows = capture_saved
        try:
            result = ree_forecast.capture_ree_forecast(
                hoy=request["hoy"],
                session=session,
                api_key="fixture-ree-key",
                captured_at="2026-01-10T09:00:00+01:00",
            )
        finally:
            forecast_db.save_forecast_rows = original_save

        saved_row = saved["rows"][0]
        return {
            **result,
            "clave_en_cabecera": (
                session.request["headers"].get("x-api-key") == "fixture-ree-key"
            ),
            "indicador": 1777 if session.request["url"].endswith("/1777") else None,
            "geo_id": session.request["params"].get("geo_ids[]"),
            "fuente_guardada": saved.get("fuente"),
            "fila_guardada": saved_row,
        }

    if accion == "scheduler_order":
        from app.tasks.scheduler import SchedulerService

        servicio = SchedulerService()
        llamadas = []
        for nombre in (
            "capture_aemet_forecast",
            "capture_ree_forecast",
            "download_ree_data",
            "download_aemet_data",
            "reconcile_own_predictions",
            "run_prediction",
        ):
            setattr(
                servicio,
                nombre,
                lambda hoy=None, nombre=nombre: llamadas.append(nombre),
            )
        servicio.run_daily_task(hoy=request["hoy"])
        return llamadas

    if accion == "scheduler_failure":
        import logging
        from app.tasks.scheduler import SchedulerService

        scheduler_logger = logging.getLogger("app.tasks.scheduler")
        records = []

        class Handler(logging.Handler):
            def emit(self, record):
                records.append(record)

        handler = Handler()
        previous_level = scheduler_logger.level
        scheduler_logger.setLevel(logging.DEBUG)
        scheduler_logger.addHandler(handler)
        service = SchedulerService()
        calls = []
        names = (
            "capture_aemet_forecast",
            "capture_ree_forecast",
            "download_ree_data",
            "download_aemet_data",
            "reconcile_own_predictions",
            "run_prediction",
        )
        for name in names:
            def run_step(hoy=None, name=name):
                calls.append(name)
                if name == "capture_aemet_forecast":
                    raise RuntimeError("fallo simulado")
                return {"estado": "ok"}

            setattr(service, name, run_step)
        try:
            results = service.run_daily_task(hoy=request["hoy"])
        finally:
            scheduler_logger.removeHandler(handler)
            scheduler_logger.setLevel(previous_level)
        return {
            "llamadas": calls,
            "resultados": results,
            "error_logged": any(
                record.levelno >= logging.ERROR
                and "capture_aemet_forecast" in record.getMessage()
                for record in records
            ),
        }

    if accion == "scheduler_schedule":
        import asyncio

        if not request.get("db_path"):
            raise ValueError("db_path es obligatorio para la prueba de scheduler")
        os.environ["DB_PATH"] = request["db_path"]
        from app.services import db_ree

        db_ree.DB_PATH = request["db_path"]
        db_ree.init_db()
        from apscheduler.schedulers import background
        import app.main as main_module

        created = {}

        class FakeScheduler:
            def __init__(self):
                self.jobs = []
                self.started = False
                self.shutdown_called = False
                created["scheduler"] = self

            def add_job(self, function, trigger, **options):
                self.jobs.append({
                    "function": function.__name__,
                    "hour": options["hour"],
                    "minute": options["minute"],
                    "timezone": options["timezone"],
                })

            def start(self):
                self.started = True

            def shutdown(self):
                self.shutdown_called = True

        class FakeThread:
            def __init__(self, target, daemon=False):
                self.target = target
                self.daemon = daemon
                self.started = False

            def start(self):
                self.started = True
                created["backfill_started"] = self.started

        original_scheduler = background.BackgroundScheduler
        original_thread = main_module.threading.Thread
        background.BackgroundScheduler = FakeScheduler
        main_module.threading.Thread = FakeThread
        try:
            app = main_module.create_app(run_background_tasks=True)

            async def exercise_lifespan():
                async with app.router.lifespan_context(app):
                    scheduler = created["scheduler"]
                    jobs = list(scheduler.jobs)
                    started = scheduler.started
                return {
                    "jobs": jobs,
                    "started": started,
                    "shutdown": scheduler.shutdown_called,
                    "backfill_started": created.get("backfill_started", False),
                }

            return asyncio.run(exercise_lifespan())
        finally:
            background.BackgroundScheduler = original_scheduler
            main_module.threading.Thread = original_thread

    if accion == "migration_rollback":
        from types import SimpleNamespace

        import migrate_render_snapshot as migration

        target_db = Path(request["db_path"]).resolve()
        source_report = Path(request["source_report"]).resolve()
        target_report = Path(request["target_report"]).resolve()
        args = SimpleNamespace(
            source_db=request["source_db"],
            target_db=str(target_db),
            source_model=request["source_model"],
            target_model=request["target_model"],
            source_report=str(source_report),
            target_report=str(target_report),
            backup_dir=request["backup_dir"],
            apply=True,
        )
        original_copy = migration._atomic_copy
        error_injected = False

        def fail_once_at_report(source, target):
            nonlocal error_injected
            if (
                not error_injected
                and Path(source).resolve() == source_report
                and Path(target).resolve() == target_report
            ):
                error_injected = True
                raise OSError("fallo de activación simulado")
            return original_copy(source, target)

        migration._atomic_copy = fail_once_at_report
        try:
            try:
                migration.migrate(args)
            except OSError as error:
                if str(error) != "fallo de activación simulado":
                    raise
            else:
                raise AssertionError("se esperaba el fallo de activación simulado")
        finally:
            migration._atomic_copy = original_copy

        with sqlite3.connect(target_db) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            sentinel = conn.execute(
                "SELECT valor FROM legacy_sentinel"
            ).fetchone()
            legacy_prediction = conn.execute(
                "SELECT prediccion_mwh FROM predictions"
            ).fetchone()
        backup_dir = Path(request["backup_dir"])
        backup_files = {path.name for path in backup_dir.iterdir()}
        return {
            "error_injected": error_injected,
            "database_restored": (
                "legacy_sentinel" in tables
                and "predictions" in tables
                and sentinel == ("solo_render",)
                and legacy_prediction == (123.0,)
            ),
            "model_restored": (
                Path(request["target_model"]).read_bytes() == b"modelo-anterior"
            ),
            "report_restored": target_report.read_bytes() == b"acta-anterior",
            "backup_exists": {
                target_db.name,
                Path(request["target_model"]).name,
                target_report.name,
            }.issubset(backup_files),
        }

    if accion == "invalid_model_health":
        if not request.get("db_path"):
            raise ValueError("db_path es obligatorio para la prueba de health")
        os.environ["DB_PATH"] = request["db_path"]
        from app.services import db_ree, model_loader

        db_ree.DB_PATH = request["db_path"]
        db_ree.init_db()
        original = model_loader.model_service
        model_loader.model_service = model_loader.ModelService(
            model_path=request["model_path"],
            expected_features=tuple(reversed(model_loader.FEATURE_COLS)),
        )
        from app.main import create_app

        try:
            app = create_app(run_background_tasks=False)
            endpoint = next(
                route.endpoint for route in app.routes
                if getattr(route, "path", None) == "/health"
            )
            response = endpoint()
            if hasattr(response, "body"):
                return {
                    "status": response.status_code,
                    "body": json.loads(response.body.decode("utf-8")),
                }
            return {"status": 200, "body": response}
        finally:
            model_loader.model_service = original

    if accion == "api_refresh_preserves":
        if not request.get("db_path"):
            raise ValueError("db_path es obligatorio para la prueba de refresh")
        os.environ["DB_PATH"] = request["db_path"]
        from app.services import db_ree
        from app.services.prediction_service import PredictionService
        from app.api import prediction as prediction_api

        db_ree.DB_PATH = request["db_path"]
        db_ree.init_db()
        objetivo = "2026-01-11"
        db_ree.save_own_prediction({
            "fecha_objetivo": objetivo,
            "fecha_emision": "2026-01-10",
            "emitida_en": "2026-01-10T03:00:00+01:00",
            "prediccion_mwh": 100,
            "modelo": "Linear Regression",
            "n_variables": 19,
            "vector_entrada": {},
            "origenes": {},
        })

        class Model:
            ready = True
            family = "Linear Regression"
            load_error = None

            def predict_vector(self, vector):
                return 999

        service = PredictionService(
            model=Model(),
            data_store=db_ree,
            clock=lambda: date.fromisoformat(request["hoy"]),
        )
        original = prediction_api.prediction_service
        prediction_api.prediction_service = service
        try:
            response = prediction_api.refresh_prediction()
        finally:
            prediction_api.prediction_service = original

        rows = db_ree.get_own_predictions(fecha_objetivo=objetivo)
        return {
            "status": response.status_code,
            "body": json.loads(response.body.decode("utf-8")),
            "count": len(rows),
            "prediccion_mwh": rows[0]["prediccion_mwh"] if rows else None,
        }

    if accion == "reconcile_incomplete_generation":
        import pandas as pd
        from app.services import db_ree
        from app.services.prediction_service import PredictionService

        if not request.get("db_path"):
            raise ValueError("db_path es obligatorio para reconciliar reales")
        os.environ["DB_PATH"] = request["db_path"]
        db_ree.DB_PATH = request["db_path"]
        db_ree.init_db()
        db_ree.save_generation_data(pd.DataFrame(request["generacion"]))
        for row in request["predicciones"]:
            db_ree.save_own_prediction({
                **row,
                "modelo": "Linear Regression",
                "n_variables": 19,
                "vector_entrada": {},
                "origenes": {},
            })

        service = PredictionService(
            data_store=db_ree,
            clock=lambda: date.fromisoformat(request["hoy"]),
        )
        actualizadas = service.reconcile_reals(request["hoy"])
        rows = db_ree.get_own_predictions(
            desde="2026-01-07",
            hasta="2026-01-09",
        )
        emisiones = {row["fecha_objetivo"]: row for row in rows}
        return {"actualizadas": actualizadas, "emisiones": emisiones}

    if accion == "forecast_archive_restore":
        if not request.get("db_path"):
            raise ValueError("db_path es obligatorio para restaurar previsiones")
        os.environ["DB_PATH"] = request["db_path"]
        from app.services import db_ree, forecast_db
        from app.services.forecast_cache import restore_forecast_archive

        db_ree.DB_PATH = request["db_path"]
        db_ree.init_db()
        hoy = date.fromisoformat(request["hoy"])
        primera = restore_forecast_archive(request["snapshot"], hoy)
        segunda = restore_forecast_archive(request["snapshot"], hoy)
        with db_ree._get_conn() as conn:
            filas = forecast_db.rows_between(
                conn,
                date.fromisoformat(request["desde"]),
                date.fromisoformat(request["hasta"]),
            )
        return {"primera": primera, "segunda": segunda, "filas": filas}

    if accion == "forecast_provisional":
        from app.services.forecast_cache import es_provisional, puede_reutilizar

        return {
            "provisional": [es_provisional(snapshot) for snapshot in request["snapshots"]],
            "reutilizar": [
                puede_reutilizar(caso.get("cache"), caso["objetivo"], caso.get("force", False), caso.get("restauradas", 0))
                for caso in request.get("casos", [])
            ],
        }

    if accion == "forecast_archive_rows":
        if not request.get("db_path"):
            raise ValueError("db_path es obligatorio para el archivo de previsiones")
        os.environ["DB_PATH"] = request["db_path"]
        from app.services import db_ree, forecast_db
        from app.services.forecast_cache import _forecast_archive_rows

        db_ree.DB_PATH = request["db_path"]
        db_ree.init_db()
        forecast_db.save_forecast_rows(None, request["rows"], "aemet")
        return _forecast_archive_rows(date.fromisoformat(request["hoy"]))

    if accion in (
        "schema",
        "own_prediction_roundtrip",
        "forecast_roundtrip",
        "forecast_payload",
        "generation_update_roundtrip",
        "generation_madrid_dates",
    ):
        if not request.get("db_path"):
            raise ValueError("db_path es obligatorio para las pruebas de BD")
        os.environ["DB_PATH"] = request["db_path"]
        from app.services import db_ree

        db_ree.DB_PATH = request["db_path"]
        db_ree.init_db()

        with db_ree._get_conn() as conn:
            if accion == "schema":
                tablas = {
                    fila[0]
                    for fila in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                columnas = {}
                for tabla in (
                    "generacion",
                    "aemet_diario",
                    "prediccion_diaria",
                    "prediccion_propia",
                ):
                    columnas[tabla] = [
                        fila[1]
                        for fila in conn.execute(f"PRAGMA table_info({tabla})")
                    ]
                return {"tablas": sorted(tablas), "columnas": columnas}

            if accion == "own_prediction_roundtrip":
                primera = request["primera"]
                misma_emision = request["misma_emision"]
                siguiente_emision = request["siguiente_emision"]
                db_ree.save_own_prediction(primera, conn=conn)
                db_ree.update_own_prediction_real(
                    primera["fecha_objetivo"], request["real_mwh"], conn=conn
                )
                db_ree.save_own_prediction(misma_emision, conn=conn)
                db_ree.save_own_prediction(siguiente_emision, conn=conn)
                conn.commit()
                return db_ree.get_own_predictions(
                    primera["fecha_objetivo"], conn=conn
                )

            if accion == "forecast_roundtrip":
                from app.services.forecast_db import save_forecast_rows

                for fuente, filas in request["capturas"]:
                    save_forecast_rows(conn, filas, fuente)
                return {
                    "aemet": conn.execute(
                        "SELECT COUNT(*) FROM prediccion_diaria WHERE fuente='aemet'"
                    ).fetchone()[0],
                    "ree": conn.execute(
                        "SELECT COUNT(*) FROM prediccion_diaria WHERE fuente='ree'"
                    ).fetchone()[0],
                }

            if accion == "forecast_payload":
                from app.services.forecast_db import save_forecast_rows
                from app.services.prediction_service import PredictionService

                for fuente, filas in request["capturas"]:
                    save_forecast_rows(conn, filas, fuente)
                service = PredictionService(clock=lambda: request["hoy"])
                return service.forecast_payload(request["hoy"])

            if accion == "generation_update_roundtrip":
                import pandas as pd

                db_ree.save_generation_data(
                    pd.DataFrame(request["initial"]), conn=conn
                )
                conn.commit()
                first = db_ree.get_generation_series(hoy=request["hoy"])
                db_ree.save_generation_data(
                    pd.DataFrame(request["update"]), conn=conn
                )
                conn.commit()
                unchanged = db_ree.get_generation_series(hoy=request["hoy"])
                db_ree.save_generation_data(
                    pd.DataFrame(request["update"]),
                    conn=conn,
                    replace_existing_dates={request["replace_date"]},
                )
                conn.commit()
                replaced = db_ree.get_generation_series(hoy=request["hoy"])
                return {
                    "initial": {key.isoformat(): value for key, value in first.items()},
                    "without_authorized_replace": {
                        key.isoformat(): value for key, value in unchanged.items()
                    },
                    "with_authorized_replace": {
                        key.isoformat(): value for key, value in replaced.items()
                    },
                }

            if accion == "generation_madrid_dates":
                import pandas as pd

                db_ree.save_generation_data(
                    pd.DataFrame(request["rows"]), conn=conn
                )
                conn.commit()
                series = db_ree.get_generation_series(hoy="2026-07-11")
                return {day.isoformat(): value for day, value in series.items()}

    if accion in ("api_unavailable", "api_refresh_unavailable", "api_cached"):
        from app.api import prediction
        from app.services.prediction_service import PredictionUnavailable

        class ServicioSimulado:
            def get_prediction(self, hoy=None):
                if accion == "api_unavailable":
                    raise PredictionUnavailable(
                        fecha=request["fecha"],
                        faltan=request.get("faltan", []),
                        avisos=request.get("avisos", []),
                    )
                return request["prediction"]

            def refresh_prediction(self, hoy=None):
                raise PredictionUnavailable(
                    fecha=request["fecha"],
                    faltan=request.get("faltan", []),
                    avisos=request.get("avisos", []),
                )

        original = prediction.prediction_service
        prediction.prediction_service = ServicioSimulado()
        try:
            if accion == "api_refresh_unavailable":
                response = prediction.refresh_prediction()
            else:
                response = prediction.get_prediction()
            if hasattr(response, "body"):
                return {
                    "status": response.status_code,
                    "body": json.loads(response.body.decode("utf-8")),
                }
            return {"status": 200, "body": response}
        finally:
            prediction.prediction_service = original

    if accion == "chart_payload":
        from app.api.charts import build_prediction_chart_payload

        return build_prediction_chart_payload(
            request["historico"],
            request["viento"],
            request["predicciones_propias"],
            request["hoy"],
            avisos=request.get("avisos", []),
        )

    if accion == "model_comparison":
        os.environ["METRICS_PATH"] = request["metrics_path"]
        from app.api.charts import get_model_comparison

        return get_model_comparison()

    raise ValueError(f"acción de prueba desconocida: {accion}")


def main():
    try:
        request = json.load(sys.stdin)
        resultado = _ejecutar(request)
        sys.stdout.write(json.dumps(_serializar(resultado), ensure_ascii=True))
    except Exception as error:
        sys.stderr.write(f"{type(error).__name__}: {error}\n")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
