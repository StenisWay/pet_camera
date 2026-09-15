// Push 服務(F4 推播通知)的前端 Repository 介面。

export interface PushRepository {
  /** platform 固定為 'web',由實作帶入,呼叫端不需指定。 */
  registerToken(token: string): Promise<void>;
  unregisterToken(pushTokenId: string): Promise<void>;
}
