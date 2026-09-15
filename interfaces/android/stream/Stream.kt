package com.petcamera.interfaces.stream

// Stream 訊令服務(F1 即時串流)。

data class TurnCredentials(
    val urls: List<String>,
    val username: String,
    val credential: String,
)

data class StreamSession(
    val sessionId: String,
    val turnCredentials: TurnCredentials,
)

interface StreamRepository {
    suspend fun createSession(deviceId: String): StreamSession
    suspend fun sendOffer(deviceId: String, sessionId: String, sdpOffer: String): String // sdpAnswer
    suspend fun endSession(deviceId: String, sessionId: String)
}
