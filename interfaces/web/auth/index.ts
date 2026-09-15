// Auth 服務(F0.1 登入註冊密碼重設 + F0.4 帳號設定)的前端 Repository 介面。
//
// Web 版 access token(1 小時)過期後由 refresh token 靜默換發(見
// 02_spec_登入註冊與密碼重設.md 第 2.3.1 節)——這是實作內部攔截器行為,
// 不是呼叫端要主動呼叫的方法,故介面不出現 refresh 相關方法。

export interface AuthRepository {
  register(email: string, password: string): Promise<void>;
  login(email: string, password: string): Promise<void>;
  /** 撤銷目前 refresh token 並清除本機憑證。僅 Web 提供(App 無登出功能)。 */
  logout(): Promise<void>;
  forgotPassword(email: string): Promise<void>;
  resetPassword(resetToken: string, newPassword: string): Promise<void>;
}

export interface AccountRepository {
  changePassword(currentPassword: string, newPassword: string): Promise<void>;
  /** 破壞性操作:跨服務串聯刪除該帳號所有裝置、事件、相簿內容、push token。 */
  deleteAccount(currentPassword: string): Promise<void>;
}
