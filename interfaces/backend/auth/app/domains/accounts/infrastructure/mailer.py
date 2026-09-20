"""寄出密碼重設連結(02_spec 第 2.4 節)。

規格刻意不指定 SMTP 服務商,所以這裡提供兩個實作:

- `LoggingEmailSender`:把連結寫進 log。本地開發與尚未接上寄信服務時用。
- `SmtpEmailSender`:標準 SMTP,收件設定由環境變數帶進來。

注意**不要**在這裡吞掉失敗:對外是否回成功是 use case 的決定(反列舉),
adapter 的責任只是誠實回報寄不出去。兩層都吞的話,連 log 都不會有。
"""

import logging
import smtplib
from email.message import EmailMessage

import anyio

from app.domains.accounts.application.ports import EmailSender

logger = logging.getLogger(__name__)

SUBJECT = "重設您的寵物攝影機密碼"
BODY = """您好,

我們收到了重設密碼的請求。請點擊以下連結設定新密碼,連結 30 分鐘後失效:

{reset_url}

如果這不是您本人的操作,請忽略這封信,您的密碼不會有任何變動。
"""


class LoggingEmailSender(EmailSender):
    """不真的寄信,只把連結寫進 log。**正式環境不可使用**:重設連結等同於
    一次性的登入憑證,寫進 log 就是把它散佈到每個看得到 log 的人手上。"""

    async def send_password_reset(self, to: str, *, reset_url: str) -> None:
        logger.info("[dev] password reset link for %s: %s", to, reset_url)


class SmtpEmailSender(EmailSender):
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        use_tls: bool = True,
        timeout: float = 10.0,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sender = sender
        self._use_tls = use_tls
        self._timeout = timeout

    async def send_password_reset(self, to: str, *, reset_url: str) -> None:
        message = EmailMessage()
        message["Subject"] = SUBJECT
        message["From"] = self._sender
        message["To"] = to
        message.set_content(BODY.format(reset_url=reset_url))
        # smtplib 是同步的:丟到工作執行緒,別把事件迴圈卡住
        await anyio.to_thread.run_sync(self._send, message)

    def _send(self, message: EmailMessage) -> None:
        with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
            if self._use_tls:
                smtp.starttls()
            if self._username:
                smtp.login(self._username, self._password)
            smtp.send_message(message)
