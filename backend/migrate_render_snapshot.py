"""Sustitución manual y reversible de los artefactos persistentes de Render.

No se importa desde la aplicación ni se ejecuta en el arranque. Para producción
requiere detener primero el servicio y pasar explícitamente `--apply`.
"""

from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import joblib


ROOT = Path(__file__).resolve().parent
FEATURES_LR19 = (
    "velmedia", "racha", "mes", "dia_semana", "dia_año",
    "eolica_lag1", "eolica_lag2", "eolica_lag3", "eolica_lag7",
    "vel_ma3", "vel_ma7", "vel_ma14",
    "racha_ma3", "racha_ma7", "racha_ma14", "eolica_ma7",
    "sol_lag1", "tmed_lag1", "eolica_prev",
)
REQUIRED_COLUMNS = {
    "generacion": (
        "datetime", "tecnologia", "tipo", "valor_MWh", "porcentaje",
    ),
    "aemet_diario": (
        "fecha", "indicativo", "nombre", "provincia", "tmed", "tmin",
        "tmax", "velmedia", "racha", "prec", "sol",
    ),
    "prediccion_diaria": (
        "fuente", "elaborado", "objetivo", "ubicacion", "uso", "viento_ms",
        "racha_ms", "tmax", "tmin", "tmed", "sol", "tramos_cielo", "orto",
        "ocaso", "uv_max", "eolica_mwh", "parte_json", "capturado_en",
    ),
    "prediccion_propia": (
        "fecha_objetivo", "fecha_emision", "emitida_en", "prediccion_mwh",
        "modelo", "n_variables", "vector_entrada", "origenes", "real_mwh",
        "error_mwh",
    ),
}


class MigrationError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def _validate_database(path: Path) -> dict:
    if not path.is_file():
        raise MigrationError(f"no existe la BD: {path}")
    uri = path.resolve().as_uri() + "?mode=ro"
    table_hashes = {}
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise MigrationError(f"PRAGMA integrity_check: {integrity}")
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        missing = sorted(set(REQUIRED_COLUMNS) - tables)
        if missing:
            raise MigrationError(f"faltan tablas canónicas: {', '.join(missing)}")
        counts = {}
        schema = {}
        for table, expected in REQUIRED_COLUMNS.items():
            actual = tuple(
                row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')
            )
            if actual != expected:
                raise MigrationError(
                    f"esquema inesperado en {table}: {actual!r}"
                )
            schema[table] = actual
            counts[table] = int(
                conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            )
            pk = [
                row[1] for row in sorted(
                    (row for row in conn.execute(f'PRAGMA table_info("{table}")') if row[5]),
                    key=lambda item: item[5],
                )
            ]
            if not pk:
                raise MigrationError(f"la tabla {table} no declara clave primaria")
            digest = hashlib.sha256()
            selected = ", ".join(f'"{column}"' for column in actual)
            order = ", ".join(f'"{column}"' for column in pk)
            cursor = conn.execute(
                f'SELECT {selected} FROM "{table}" ORDER BY {order}'
            )
            for record in cursor:
                line = json.dumps(
                    record,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
                digest.update(line)
                digest.update(b"\n")
            table_hashes[table] = digest.hexdigest()
    return {
        "file_sha256": _sha256(path),
        "schema": schema,
        "counts": counts,
        "table_sha256": table_hashes,
    }


def _validate_model(model_path: Path, report_path: Path) -> dict:
    if not model_path.is_file():
        raise MigrationError(f"no existe el modelo: {model_path}")
    if not report_path.is_file():
        raise MigrationError(f"no existe el acta: {report_path}")
    artifact = joblib.load(model_path)
    if not isinstance(artifact, dict):
        raise MigrationError("el modelo no contiene el diccionario esperado")
    if artifact.get("familia") != "Linear Regression":
        raise MigrationError("la familia del modelo no es Linear Regression")
    if tuple(artifact.get("features") or ()) != FEATURES_LR19:
        raise MigrationError("el modelo no tiene el contrato ordenado LR-19")
    if artifact.get("usa_scaler") is not True:
        raise MigrationError("el artefacto LR-19 debe declarar usa_scaler=True")
    model = artifact.get("modelo")
    scaler = artifact.get("scaler")
    if getattr(model, "n_features_in_", None) != len(FEATURES_LR19):
        raise MigrationError("el estimador no acepta exactamente 19 features")
    if getattr(scaler, "n_features_in_", None) != len(FEATURES_LR19):
        raise MigrationError("el scaler no acepta exactamente 19 features")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    declared = report.get("modelo", {})
    if tuple(declared.get("features_produccion") or ()) != FEATURES_LR19:
        raise MigrationError("el acta no declara las 19 features del artefacto")
    if declared.get("familia_produccion") != "Linear Regression":
        raise MigrationError("el acta y el modelo declaran familias distintas")
    return {
        "model_sha256": _sha256(model_path),
        "report_sha256": _sha256(report_path),
        "familia": artifact["familia"],
        "features": list(artifact["features"]),
        "usa_scaler": artifact["usa_scaler"],
    }


def _backup_database(source: Path, backup: Path) -> None:
    backup.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(source)
    dst = sqlite3.connect(backup)
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def _atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(fd)
    temporary = Path(tmp_name)
    try:
        shutil.copyfile(source, temporary)
        with temporary.open("r+b") as archivo:
            os.fsync(archivo.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_database_copy(source: Path, target: Path,
                          require_canonical: bool = True) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(fd)
    temporary = Path(tmp_name)
    try:
        src = sqlite3.connect(source)
        dst = sqlite3.connect(temporary)
        try:
            src.backup(dst)
            dst.commit()
            journal_mode = dst.execute("PRAGMA journal_mode").fetchone()[0].lower()
            if journal_mode == "wal":
                checkpoint = dst.execute(
                    "PRAGMA wal_checkpoint(TRUNCATE)"
                ).fetchone()
                if checkpoint and int(checkpoint[0]) != 0:
                    raise MigrationError(
                        "no se pudo cerrar el WAL de la copia temporal"
                    )
                mode = dst.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
                if str(mode).lower() != "delete":
                    raise MigrationError(
                        "no se pudo dejar la copia temporal sin WAL"
                    )
        finally:
            dst.close()
            src.close()
        if require_canonical:
            _validate_database(temporary)
        else:
            with closing(sqlite3.connect(temporary)) as connection:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise MigrationError(f"backup no íntegro al restaurar: {integrity}")
        os.replace(temporary, target)
    finally:
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{temporary}{suffix}")
            if sidecar.exists():
                sidecar.unlink()
        if temporary.exists():
            temporary.unlink()


def migrate(args) -> dict:
    source_db = Path(args.source_db).resolve()
    target_db = Path(args.target_db).resolve()
    source_model = Path(args.source_model).resolve()
    target_model = Path(args.target_model).resolve()
    source_report = Path(args.source_report).resolve()
    target_report = Path(args.target_report).resolve()
    backup_dir = Path(args.backup_dir).resolve()

    if source_db == target_db or source_model == target_model:
        raise MigrationError("origen y destino no pueden ser la misma ruta")
    database_manifest = _validate_database(source_db)
    model_manifest = _validate_model(source_model, source_report)

    if not args.apply:
        return {
            "applied": False,
            "source_db": str(source_db),
            "database": database_manifest,
            "model": model_manifest,
        }

    backup_dir.mkdir(parents=True, exist_ok=False)
    backup_db = backup_dir / target_db.name
    backup_model = backup_dir / target_model.name
    backup_report = backup_dir / target_report.name
    existed = {
        "db": target_db.exists(),
        "model": target_model.exists(),
        "report": target_report.exists(),
    }
    db_touched = False
    model_replaced = False
    report_replaced = False

    try:
        if existed["db"]:
            _backup_database(target_db, backup_db)
        if existed["model"]:
            shutil.copy2(target_model, backup_model)
        if existed["report"]:
            shutil.copy2(target_report, backup_report)

        if existed["db"]:
            conn = sqlite3.connect(target_db)
            try:
                checkpoint = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                if checkpoint and int(checkpoint[0]) != 0:
                    raise MigrationError("no se pudo cerrar el WAL de la BD activa")
            finally:
                conn.close()
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{target_db}{suffix}")
            if sidecar.exists():
                shutil.copy2(sidecar, backup_dir / f"{target_db.name}{suffix}")
                sidecar.unlink()
                db_touched = True

        _atomic_database_copy(source_db, target_db)
        db_touched = True
        _atomic_copy(source_model, target_model)
        model_replaced = True
        _atomic_copy(source_report, target_report)
        report_replaced = True

        installed_database = _validate_database(target_db)
        installed_model = _validate_model(target_model, target_report)
        if (
            installed_database["schema"] != database_manifest["schema"]
            or installed_database["counts"] != database_manifest["counts"]
            or installed_database["table_sha256"] != database_manifest["table_sha256"]
        ):
            raise MigrationError("el contenido instalado no coincide con la instantánea")
        if installed_model["model_sha256"] != model_manifest["model_sha256"]:
            raise MigrationError("el modelo instalado no coincide con el aprobado")
        if installed_model["report_sha256"] != model_manifest["report_sha256"]:
            raise MigrationError("el acta instalada no coincide con la aprobada")
        manifest = {
            "applied": True,
            "backup_dir": str(backup_dir),
            "backup_files": sorted(path.name for path in backup_dir.iterdir()),
            "database": installed_database,
            "model": installed_model,
        }
        (backup_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        if db_touched and existed["db"] and backup_db.exists():
            _atomic_database_copy(backup_db, target_db, require_canonical=False)
        elif db_touched and target_db.exists():
            target_db.unlink()
        if model_replaced and existed["model"] and backup_model.exists():
            _atomic_copy(backup_model, target_model)
        elif model_replaced and target_model.exists():
            target_model.unlink()
        if report_replaced and existed["report"] and backup_report.exists():
            _atomic_copy(backup_report, target_report)
        elif report_replaced and target_report.exists():
            target_report.unlink()
        raise

    return manifest


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Reemplaza una vez BD/modelo de destino tras backup."
    )
    parser.add_argument(
        "--source-db",
        default=str(ROOT / "data" / "ree_generacion.db"),
    )
    parser.add_argument(
        "--target-db",
        default=os.environ.get("DB_PATH", "/app/data/ree_generacion.db"),
    )
    parser.add_argument(
        "--source-model",
        default=str(ROOT / "modelos" / "lr_eolica.joblib"),
    )
    parser.add_argument(
        "--target-model",
        default=os.environ.get("MODEL_PATH", "/app/modelos/lr_eolica.joblib"),
    )
    parser.add_argument(
        "--source-report",
        default=str(ROOT / "modelos" / "familia_como_modelo.json"),
    )
    parser.add_argument(
        "--target-report",
        default=os.environ.get(
            "METRICS_PATH", "/app/modelos/familia_como_modelo.json"
        ),
    )
    parser.add_argument(
        "--backup-dir",
        default=os.environ.get("BACKUP_DIR", ""),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="confirma que el servicio está parado y aplica el reemplazo",
    )
    args = parser.parse_args(argv)
    if not args.backup_dir:
        stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S")
        args.backup_dir = str(Path(args.target_db).resolve().parent / "backups" / stamp)
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        result = migrate(args)
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not args.apply:
        print("Previsualización: no se cambió ningún archivo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
