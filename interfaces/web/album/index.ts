// Album 服務(F6 相簿與 Google Drive 匯出)的前端 Repository 介面。
//
// AlbumItem 刻意不匯入 media 服務的 MediaItem 型別,即使兩者對應同一張後端資料表——
// 服務邊界獨立,理由見 rule_doc/功能需求/13_ADR_微服務與雙節點部署.md 第 1 節。

import type { Page } from '../common';

export type DriveExportStatus = 'not_exported' | 'exporting' | 'exported' | 'failed';

export interface AlbumItem {
  id: string;
  deviceId: string;
  type: 'photo' | 'clip';
  mediaUrl: string | null;
  thumbnailUrl: string | null;
  durationSec: number | null;
  capturedAt: string;
  driveExportStatus: DriveExportStatus;
}

export interface AlbumRepository {
  list(options?: { cursor?: string; limit?: number; date?: string }): Promise<Page<AlbumItem>>;
  remove(mediaItemId: string): Promise<void>;
  getGoogleDriveOAuthUrl(): Promise<{ url: string }>;
  completeGoogleDriveOAuth(code: string): Promise<void>;
  exportToGoogleDrive(mediaItemIds: string[]): Promise<void>;
}
