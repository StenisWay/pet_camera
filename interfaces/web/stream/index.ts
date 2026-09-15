// Stream 訊令服務(F1 即時串流)的前端 Repository 介面。

export interface TurnCredentials {
  urls: string[];
  username: string;
  credential: string;
}

export interface StreamSession {
  sessionId: string;
  turnCredentials: TurnCredentials;
}

export interface StreamRepository {
  createSession(deviceId: string): Promise<StreamSession>;
  sendOffer(deviceId: string, sessionId: string, sdpOffer: string): Promise<{ sdpAnswer: string }>;
  endSession(deviceId: string, sessionId: string): Promise<void>;
}
