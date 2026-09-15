package com.petcamera.interfaces.device

import java.time.Instant

// Device 服務(F0.2 裝置配對 + F0.3 裝置管理)。
// 注意:這裡的「裝置」是攝影機硬體,與 push 服務的用戶端裝置 token 是不同概念。

enum class DeviceStatus { PENDING, PAIRED, OFFLINE }

data class Device(
    val id: String,
    val name: String,
    val status: DeviceStatus,
    val lastSeenAt: Instant?,
    val createdAt: Instant,
)

interface DeviceRepository {
    suspend fun list(): List<Device>
    suspend fun pair(pairingCode: String): Device
    suspend fun rename(deviceId: String, name: String)
    /** 破壞性操作:跨服務串聯移除該裝置的事件與影片(見資料模型第 6 節)。 */
    suspend fun remove(deviceId: String)
}
