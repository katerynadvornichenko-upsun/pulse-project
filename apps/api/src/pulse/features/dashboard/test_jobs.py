from sqlmodel import Session, col, select

from pulse.features.dashboard.jobs import daily_rollup_sync
from pulse.features.issues.schemas import IssueCreate
from pulse.features.issues.service import change_status, create_issue
from pulse.features.projects.schemas import ProjectCreate
from pulse.features.projects.service import create_project
from pulse.models import ActivityEvent, IssueStatus


def test_rollup_records_summary_event(session: Session) -> None:
    project = create_project(session, ProjectCreate(name="P"))
    create_issue(session, IssueCreate(title="open", project_id=project.id))
    done = create_issue(session, IssueCreate(title="done", project_id=project.id))
    change_status(session, done.id, IssueStatus.DONE)

    event = daily_rollup_sync(session)

    assert event.entity_type == "dashboard"
    assert event.action == "rollup"
    assert "1 projects" in event.message
    assert "2 issues" in event.message
    assert "1 open" in event.message

    stored = session.exec(
        select(ActivityEvent).where(col(ActivityEvent.action) == "rollup")
    ).one()
    assert stored.id == event.id


def test_rollup_on_empty_database(session: Session) -> None:
    event = daily_rollup_sync(session)
    assert "0 projects" in event.message
    assert "0 issues" in event.message
