"""Business logic for this slice. Services take a Session, never create one.

Raise pulse.lib.errors.NotFoundError for missing entities (mapped to 404).
Record an ActivityEvent for every state change so the dashboard timeline works.
"""

# import uuid
#
# from sqlmodel import Session, select
#
# from pulse.lib.errors import NotFoundError
# from pulse.models import ActivityEvent, Thing
#
#
# def list_things(session: Session) -> list[Thing]:
#     return list(session.exec(select(Thing)).all())
