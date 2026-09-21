from app.domains.drive_export.domain.entities import DriveConnection
from app.domains.drive_export.infrastructure.orm import DriveCredentialRow


def to_entity(row: DriveCredentialRow) -> DriveConnection:
    return DriveConnection(
        id=row.id,
        owner_id=row.user_id,
        refresh_token=row.refresh_token,
        connected_at=row.connected_at,
        folder_id=row.drive_folder_id,
    )


def to_new_row(connection: DriveConnection) -> DriveCredentialRow:
    return DriveCredentialRow(
        id=connection.id,
        user_id=connection.owner_id,
        refresh_token=connection.refresh_token,
        drive_folder_id=connection.folder_id,
        connected_at=connection.connected_at,
    )


def apply_to_row(connection: DriveConnection, row: DriveCredentialRow) -> None:
    row.refresh_token = connection.refresh_token
    row.drive_folder_id = connection.folder_id
    row.connected_at = connection.connected_at
