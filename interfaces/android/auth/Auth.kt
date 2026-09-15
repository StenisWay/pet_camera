package com.petcamera.interfaces.auth

// Auth 服務(F0.1 登入註冊密碼重設 + F0.4 帳號設定)。
//
// App 版 token 為單一長效 token(180 天,使用中自動滑動展延,見
// 02_spec_登入註冊與密碼重設.md 第 2.3.2 節),故沒有 refresh 方法;
// App 依規格書 2.5 節不提供登出功能,AuthRepository 沒有 logout()。

interface AuthRepository {
    suspend fun register(email: String, password: String)
    suspend fun login(email: String, password: String)
    suspend fun forgotPassword(email: String)
    suspend fun resetPassword(resetToken: String, newPassword: String)
}

interface AccountRepository {
    suspend fun changePassword(currentPassword: String, newPassword: String)
    /** 破壞性操作:跨服務串聯刪除該帳號所有裝置、事件、相簿內容、push token。 */
    suspend fun deleteAccount(currentPassword: String)
}
