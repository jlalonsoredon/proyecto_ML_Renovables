"""Endpoints internos para el workflow de GitHub Actions (spec 010).

No forman parte del contrato público: el router se registra con
`include_in_schema=False` y no se anuncia en `/`.
"""

import logging
import os
import secrets
import threading
import time
from collections import deque

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..services import forecast_cache
from ..services.redaction import redact_secrets

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/internal", tags=["internal"], include_in_schema=False)

MAX_FALLOS = 5
VENTANA_S = 60


class RefreshRequest(BaseModel):
    """Snapshot publicado que el workflow envía como archivo de predicciones."""

    snapshot_anterior: dict | None = None

_fallos: dict[str, deque] = {}
_fallos_lock = threading.Lock()


def _ip(request: Request) -> str:
    # Detrás del proxy de Render, uvicorn con --proxy-headers deja aquí la IP real.
    return request.client.host if request.client else "desconocida"


def _fallos_recientes(ip: str, ahora: float) -> int:
    registro = _fallos.get(ip)
    if registro is None:
        return 0
    while registro and ahora - registro[0] >= VENTANA_S:
        registro.popleft()
    if not registro:
        del _fallos[ip]
        return 0
    return len(registro)


def _rechazar(request: Request, motivo: str, recibido: str, esperado: str):
    ahora = time.monotonic()
    ip = _ip(request)
    with _fallos_lock:
        _fallos_recientes(ip, ahora)
        _fallos.setdefault(ip, deque()).append(ahora)
        total = len(_fallos[ip])
    logger.warning(
        "%s",
        redact_secrets(
            f"Intento rechazado en {request.url.path}: ip={ip} motivo={motivo} "
            f"fallos_recientes={total}",
            recibido,
            esperado,
        ),
    )
    raise HTTPException(
        status_code=401,
        detail="No autorizado",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_token(request: Request) -> None:
    esperado = os.environ.get("REFRESH_TOKEN", "")
    if not esperado:
        logger.error("REFRESH_TOKEN no está configurada; el endpoint interno queda cerrado")
        raise HTTPException(status_code=503, detail="refresh_no_configurado")

    ip = _ip(request)
    with _fallos_lock:
        bloqueado = _fallos_recientes(ip, time.monotonic()) >= MAX_FALLOS
    if bloqueado:
        logger.warning("Intento bloqueado en %s: ip=%s motivo=rate_limit", request.url.path, ip)
        raise HTTPException(
            status_code=429,
            detail="demasiados_intentos",
            headers={"Retry-After": str(VENTANA_S)},
        )

    cabecera = request.headers.get("authorization", "")
    esquema, _, recibido = cabecera.partition(" ")
    if esquema.lower() != "bearer" or not recibido.strip():
        _rechazar(request, "token_ausente", cabecera, esperado)
    recibido = recibido.strip()
    if not secrets.compare_digest(recibido.encode("utf-8"), esperado.encode("utf-8")):
        _rechazar(request, "token_incorrecto", recibido, esperado)


@router.post("/forecast/refresh", dependencies=[Depends(require_token)])
def refresh_forecast(force: bool = False, body: RefreshRequest | None = None):
    try:
        return forecast_cache.refresh(
            force=force,
            snapshot_anterior=body.snapshot_anterior if body else None,
        )
    except forecast_cache.RunInProgress:
        return JSONResponse(status_code=409, content={"detail": "run_in_progress"})
    except forecast_cache.SnapshotInvalid as error:
        return JSONResponse(
            status_code=502,
            content={"detail": "snapshot_invalido", "problemas": error.problemas},
        )


@router.get("/forecast/status", dependencies=[Depends(require_token)])
def forecast_status():
    return {"cache": forecast_cache.cached()}
