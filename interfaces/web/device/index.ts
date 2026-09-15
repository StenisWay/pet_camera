// Device 服務(F0.2 裝置配對 + F0.3 裝置管理)的前端 Repository 介面。
// 注意:這裡的「裝置」是攝影機硬體,與 push 服務的用戶端裝置 token 是不同概念。

export type DeviceStatus = 'pending' | 'paired' | 'offline';

export interface Device {
  id: string;
  name: string;
  status: DeviceStatus;
  lastSeenAt: string | null; // ISO 8601
  createdAt: string;
}

export interface DeviceRepository {
  list(): Promise<Device[]>;
  pair(pairingCode: string): Promise<Device>;
  rename(deviceId: string, name: string): Promise<void>;
  /** 破壞性操作:跨服務串聯移除該裝置的事件與影片(見資料模型第 6 節)。 */
  remove(deviceId: string): Promise<void>;
}
