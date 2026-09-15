package com.petcamera.interfaces.push

// Push 服務(F4 推播通知)。

interface PushRepository {
    /** platform 固定為 'app',由實作帶入,呼叫端不需指定。 */
    suspend fun registerToken(fcmToken: String)
    suspend fun unregisterToken(pushTokenId: String)
}
