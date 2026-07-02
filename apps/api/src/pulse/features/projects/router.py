import uuid

from fastapi import APIRouter, status

from pulse.features.projects import service
from pulse.features.projects.schemas import ProjectCreate, ProjectRead, ProjectUpdate
from pulse.lib.db import SessionDep

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectRead])
def list_projects(session: SessionDep) -> list[ProjectRead]:
    return [ProjectRead.model_validate(p) for p in service.list_projects(session)]


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(data: ProjectCreate, session: SessionDep) -> ProjectRead:
    return ProjectRead.model_validate(service.create_project(session, data))


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: uuid.UUID, session: SessionDep) -> ProjectRead:
    return ProjectRead.model_validate(service.get_project(session, project_id))


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: uuid.UUID, data: ProjectUpdate, session: SessionDep
) -> ProjectRead:
    return ProjectRead.model_validate(service.update_project(session, project_id, data))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: uuid.UUID, session: SessionDep) -> None:
    service.delete_project(session, project_id)
