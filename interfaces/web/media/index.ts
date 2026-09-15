// Media 服務(F5 剪輯與截圖)的前端 Repository 介面。

export type MediaItemStatus = 'processing' | 'ready' | 'failed';

export interface MediaItem {
  id: string;
  deviceId: string;
  sourceEventId: string | null;
  type: 'photo' | 'clip';
  mediaUrl: string | null; // status=ready 後才有值
  thumbnailUrl: string | null; // 僅 type=clip 有值
  durationSec: number | null; // 僅 type=clip 有值
  status: MediaItemStatus;
  capturedAt: string;
}

export interface MediaRepository {
  captureScreenshotFromLiveView(deviceId: string): Promise<MediaItem>;
  captureScreenshotFromEvent(eventId: string): Promise<MediaItem>;
  /** 單次剪輯上限 5 分鐘(CLIP_003),由呼叫端在 UI 先行檢查。 */
  createClip(eventId: string, startSec: number, endSec: number): Promise<MediaItem>;
  /** status=processing 時輪詢用。 */
  getMediaItem(mediaItemId: string): Promise<MediaItem>;
}
