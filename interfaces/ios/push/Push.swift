import Foundation

// Push 服務(F4 推播通知)。

protocol PushRepository {
    /// platform 固定為 'app',由實作帶入,呼叫端不需指定。
    func registerToken(_ deviceToken: String) async throws
    func unregisterToken(pushTokenId: String) async throws
}
