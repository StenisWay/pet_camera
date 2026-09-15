import Foundation

// Event 服務(F2 事件偵測的讀取面 + F3 時間軸與事件歷史)。
// F2 本身是背景 worker,不對外提供 API;App 只透過本服務的時間軸 API 讀取結果。

enum EventStatus: String, Codable {
    case processing
    case ready
    case failed
}

/// 命名為 CameraEvent 避免與 Swift/Foundation 慣用的 Event 語意混淆。
struct CameraEvent: Codable {
    let id: String
    let deviceId: String
    let eventType: String // "motion"
    let confidenceScore: Double // 0.00 - 1.00
    let status: EventStatus
    let thumbnailUrl: URL?
    let durationSec: Int
    let startedAt: Date
    let endedAt: Date?
    let isRead: Bool
}

protocol TimelineRepository {
    func listEvents(
        deviceId: String, cursor: String?, limit: Int, date: String?
    ) async throws -> Page<CameraEvent>
    /// 一次性 presigned URL(10 分鐘有效),點擊當下才呼叫,不預先批次取得。
    func getPlaybackUrl(eventId: String) async throws -> URL
    func markRead(eventId: String) async throws
}
