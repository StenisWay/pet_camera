package com.petcamera.interfaces.media

import java.time.Instant

// Media 服務(F5 剪輯與截圖)。

enum class MediaItemStatus { PROCESSING, READY, FAILED }

enum class MediaItemType { PHOTO, CLIP }

data class MediaItem(
    val id: String,
    val deviceId: String,
    val sourceEventId: String?,
    val type: MediaItemType,
    val mediaUrl: String?, // status=ready 後才有值
    val thumbnailUrl: String?, // 僅 type=clip 有值
    val durationSec: Int?, // 僅 type=clip 有值
    val status: MediaItemStatus,
    val capturedAt: Instant,
)

interface MediaRepository {
    suspend fun captureScreenshotFromLiveView(deviceId: String): MediaItem
    suspend fun captureScreenshotFromEvent(eventId: String): MediaItem
    /** 單次剪輯上限 5 分鐘(CLIP_003),由呼叫端在 UI 先行檢查。 */
    suspend fun createClip(eventId: String, startSec: Int, endSec: Int): MediaItem
    /** status=processing 時輪詢用。 */
    suspend fun getMediaItem(mediaItemId: String): MediaItem
}
