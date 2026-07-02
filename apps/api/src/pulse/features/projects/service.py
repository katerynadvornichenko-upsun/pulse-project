import uuid

from sqlmodel import Session, col, select

from pulse.features.projects.schemas import ProjectCreate, ProjectUpdate
from pulse.lib.errors import NotFoundError
from pulse.models import ActivityEvent, Project, utcnow


def _record(session: Session, project: Project, action: str) -> None:
    session.add(
        ActivityEvent(
            entity_type="project",
            entity_id=project.id,
            action=action,
            message=f"Project '{project.name}' {action}",
        )
    )


def list_projects(session: Session) -> list[Project]:
    return list(session.exec(select(Project).order_by(col(Project.created_at))).all())


def get_project(session: Session, project_id: uuid.UUID) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise NotFoundError("Project", project_id)
    return project


def create_project(session: Session, data: ProjectCreate) -> Project:
    project = Project(name=data.name, description=data.description)
    session.add(project)
    _record(session, project, "created")
    session.commit()
    session.refresh(project)
    return project


def update_project(session: Session, project_id: uuid.UUID, data: ProjectUpdate) -> Project:
    project = get_project(session, project_id)
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in changes.items():
        setattr(project, key, value)
    project.updated_at = utcnow()
    session.add(project)
    _record(session, project, "updated")
    session.commit()
    session.refresh(project)
    return project


def delete_project(session: Session, project_id: uuid.UUID) -> None:
    project = get_project(session, project_id)
    _record(session, project, "deleted")
    session.delete(project)
    session.commit()
