import Foundation

// Media 服務(F5 剪輯與截圖)。

enum MediaItemStatus: String, Codable {
    case processing
    case ready
    case failed
}

enum MediaItemType: String, Codable {
    case photo
    case clip
}

struct MediaItem: Codable {
    let id: String
    let deviceId: String
    let sourceEventId: String?
    let type: MediaItemType
    let mediaUrl: URL? // status=ready 後才有值
    let thumbnailUrl: URL? // 僅 type=clip 有值
    let durationSec: Int? // 僅 type=clip 有值
    let status: MediaItemStatus
    let capturedAt: Date
}

protocol MediaRepository {
    func captureScreenshotFromLiveView(deviceId: String) async throws -> MediaItem
    func captureScreenshotFromEvent(eventId: String) async throws -> MediaItem
    /// 單次剪輯上限 5 分鐘(CLIP_003),由呼叫端在 UI 先行檢查。
    func createClip(eventId: String, startSec: Int, endSec: Int) async throws -> MediaItem
    /// status=processing 時輪詢用。
    func getMediaItem(mediaItemId: String) async throws -> MediaItem
}
