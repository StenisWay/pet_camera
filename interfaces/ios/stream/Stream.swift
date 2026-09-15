import Foundation

// Stream 訊令服務(F1 即時串流)。

struct TurnCredentials {
    let urls: [String]
    let username: String
    let credential: String
}

struct StreamSession {
    let sessionId: String
    let turnCredentials: TurnCredentials
}

protocol StreamRepository {
    func createSession(deviceId: String) async throws -> StreamSession
    func sendOffer(deviceId: String, sessionId: String, sdpOffer: String) async throws -> String // sdpAnswer
    func endSession(deviceId: String, sessionId: String) async throws
}
