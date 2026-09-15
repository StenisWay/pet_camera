package com.petcamera.interfaces.event

import com.petcamera.interfaces.Page
import java.time.Instant

// Event 服務(F2 事件偵測的讀取面 + F3 時間軸與事件歷史)。
// F2 本身是背景 worker,不對外提供 API;App 只透過本服務的時間軸 API 讀取結果。

enum class EventStatus { PROCESSING, READY, FAILED }

/** 命名為 CameraEvent 避免與 Android/Kotlin 慣用的 Event 語意混淆。 */
data class CameraEvent(
    val id: String,
    val deviceId: String,
    val eventType: String, // "motion"
    val confidenceScore: Double, // 0.00 - 1.00
    val status: EventStatus,
    val thumbnailUrl: String?,
    val durationSec: Int,
    val startedAt: Instant,
    val endedAt: Instant?,
    val isRead: Boolean,
)

interface TimelineRepository {
    suspend fun listEvents(
        deviceId: String,
        cursor: String? = null,
        limit: Int = 20,
        date: String? = null,
    ): Page<CameraEvent>

    /** 一次性 presigned URL(10 分鐘有效),點擊當下才呼叫,不預先批次取得。 */
    suspend fun getPlaybackUrl(eventId: String): String
    suspend fun markRead(eventId: String)
}
