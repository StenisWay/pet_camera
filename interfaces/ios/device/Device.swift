import Foundation

// Device 服務(F0.2 裝置配對 + F0.3 裝置管理)。
// 注意:這裡的「裝置」是攝影機硬體,與 push 服務的用戶端裝置 token 是不同概念。

enum DeviceStatus: String, Codable {
    case pending
    case paired
    case offline
}

struct Device: Codable {
    let id: String
    let name: String
    let status: DeviceStatus
    let lastSeenAt: Date?
    let createdAt: Date
}

protocol DeviceRepository {
    func list() async throws -> [Device]
    func pair(pairingCode: String) async throws -> Device
    func rename(deviceId: String, name: String) async throws
    /// 破壞性操作:跨服務串聯移除該裝置的事件與影片(見資料模型第 6 節)。
    func remove(deviceId: String) async throws
}
