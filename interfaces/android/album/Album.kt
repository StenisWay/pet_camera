package com.petcamera.interfaces.album

import com.petcamera.interfaces.Page
import java.time.Instant

// Album 服務(F6 相簿與 Google Drive 匯出)。
//
// AlbumItem 刻意不匯入 media 服務的 MediaItem 型別,即使兩者對應同一張後端資料表——
// 服務邊界獨立,理由見 rule_doc/功能需求/13_ADR_微服務與雙節點部署.md 第 1 節。

enum class DriveExportStatus { NOT_EXPORTED, EXPORTING, EXPORTED, FAILED }

data class AlbumItem(
    val id: String,
    val deviceId: String,
    val type: String, // "photo" / "clip"
    val mediaUrl: String?,
    val thumbnailUrl: String?,
    val durationSec: Int?,
    val capturedAt: Instant,
    val driveExportStatus: DriveExportStatus,
)

interface AlbumRepository {
    suspend fun list(cursor: String? = null, limit: Int = 30, date: String? = null): Page<AlbumItem>
    suspend fun remove(mediaItemId: String)
    suspend fun getGoogleDriveOAuthUrl(): String
    suspend fun completeGoogleDriveOAuth(code: String)
    suspend fun exportToGoogleDrive(mediaItemIds: List<String>)
}
