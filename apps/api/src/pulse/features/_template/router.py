"""HTTP layer for this slice: thin, delegates to service.py.

Register the router in apps/api/src/pulse/main.py:
    app.include_router(things_router)
"""

from fastapi import APIRouter

router = APIRouter(prefix="/things", tags=["things"])

# from pulse.lib.db import SessionDep
#
# @router.get("", response_model=list[ThingRead])
# def list_things(session: SessionDep) -> list[ThingRead]:
#     return [ThingRead.model_validate(t) for t in service.list_things(session)]
