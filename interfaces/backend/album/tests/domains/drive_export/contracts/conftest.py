from dataclasses import dataclass
from typing import Protocol

import pytest

from app.domains.drive_export.application.ports import DriveExportUnitOfWork
from app.domains.drive_export.infrastructure.unit_of_work import SqlAlchemyDriveExportUnitOfWork
from tests.domains.drive_export.fakes import FakeDriveExportUnitOfWork


class Store(Protocol):
    def uow(self) -> DriveExportUnitOfWork: ...


@dataclass
class FakeStore:
    shared: FakeDriveExportUnitOfWork

    def uow(self) -> DriveExportUnitOfWork:
        return self.shared


@dataclass
class SqlStore:
    session_factory: object

    def uow(self) -> DriveExportUnitOfWork:
        return SqlAlchemyDriveExportUnitOfWork(self.session_factory)


@pytest.fixture(params=["fake", pytest.param("sqlalchemy", marks=pytest.mark.integration)])
def store(request) -> Store:
    if request.param == "fake":
        return FakeStore(FakeDriveExportUnitOfWork())
    return SqlStore(request.getfixturevalue("session_factory"))
