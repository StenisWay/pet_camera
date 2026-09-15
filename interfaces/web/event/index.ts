// Event 服務(F2 事件偵測的讀取面 + F3 時間軸與事件歷史)的前端 Repository 介面。
// F2 本身是背景 worker,不對外提供 API;前端只透過本服務的時間軸 API 讀取結果。

import type { Page } from '../common';

export type EventStatus = 'processing' | 'ready' | 'failed';

// 命名為 CameraEvent 而非 Event,避免與 DOM 全域的 Event 型別衝突。
export interface CameraEvent {
  id: string;
  deviceId: string;
  eventType: 'motion';
  confidenceScore: number; // 0.00 - 1.00
  status: EventStatus;
  thumbnailUrl: string | null; // 後端已解析為可直接使用的網址
  durationSec: number;
  startedAt: string;
  endedAt: string | null;
  isRead: boolean;
}

export interface TimelineRepository {
  listEvents(
    deviceId: string,
    options?: { cursor?: string; limit?: number; date?: string }
  ): Promise<Page<CameraEvent>>;
  /** 一次性 presigned URL(10 分鐘有效),點擊當下才呼叫,不預先批次取得。 */
  getPlaybackUrl(eventId: string): Promise<{ url: string }>;
  markRead(eventId: string): Promise<void>;
}
