"""CareBridge API routers.

Each module exposes an ``APIRouter`` named ``router``. ``ALL_ROUTERS`` collects
them in a stable order for ``src.api.main.create_app`` to mount.
"""

from fastapi import APIRouter

from src.api.routers.alerts import router as alerts_router
from src.api.routers.appointments import router as appointments_router
from src.api.routers.appointments_crud import router as appointments_crud_router
from src.api.routers.approvals import router as approvals_router
from src.api.routers.audit import router as audit_router
from src.api.routers.auth import router as auth_router
from src.api.routers.deliveries import router as deliveries_router
from src.api.routers.health import router as health_router
from src.api.routers.mcp import router as mcp_router
from src.api.routers.medications import router as medications_router
from src.api.routers.medications_crud import router as medications_crud_router
from src.api.routers.query import router as query_router
from src.api.routers.settings_crud import router as settings_crud_router
from src.api.routers.status import router as status_router

ALL_ROUTERS: list[APIRouter] = [
    health_router,
    auth_router,
    status_router,
    alerts_router,
    approvals_router,
    audit_router,
    query_router,
    medications_router,
    medications_crud_router,
    appointments_router,
    appointments_crud_router,
    deliveries_router,
    settings_crud_router,
    mcp_router,
]

__all__ = ["ALL_ROUTERS"]
