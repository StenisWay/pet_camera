import Foundation

// Album 服務(F6 相簿與 Google Drive 匯出)。
//
// AlbumItem 刻意不匯入 media 服務的 MediaItem 型別,即使兩者對應同一張後端資料表——
// 服務邊界獨立,理由見 rule_doc/功能需求/13_ADR_微服務與雙節點部署.md 第 1 節。

enum DriveExportStatus: String, Codable {
    case notExported = "not_exported"
    case exporting
    case exported
    case failed
}

struct AlbumItem: Codable {
    let id: String
    let deviceId: String
    let type: String // "photo" / "clip"
    let mediaUrl: URL?
    let thumbnailUrl: URL?
    let durationSec: Int?
    let capturedAt: Date
    let driveExportStatus: DriveExportStatus
}

protocol AlbumRepository {
    func list(cursor: String?, limit: Int, date: String?) async throws -> Page<AlbumItem>
    func remove(mediaItemId: String) async throws
    func getGoogleDriveOAuthUrl() async throws -> URL
    func completeGoogleDriveOAuth(code: String) async throws
    func exportToGoogleDrive(mediaItemIds: [String]) async throws
}
