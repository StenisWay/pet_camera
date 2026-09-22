"""註冊帳號(02_spec 第 2.2 節)。

註冊成功不自動登入(見 screens/*/01_page_登入註冊忘記密碼.md),所以這裡不呼叫
SessionService——使用者拿到成功回應後被導回登入頁。
"""

from app.domains.accounts.application.dtos import RegisteredUser, RegisterUserCommand
from app.domains.accounts.application.ports import AccountsUnitOfWork
from app.domains.accounts.domain.entities import User
from app.domains.accounts.domain.services import PasswordHasher
from app.domains.accounts.domain.value_objects import Email, RawPassword
from app.shared_kernel.ports import Clock, IdGenerator


class RegisterUser:
    def __init__(
        self,
        uow: AccountsUnitOfWork,
        *,
        hasher: PasswordHasher,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self.uow = uow
        self.hasher = hasher
        self.clock = clock
        self.ids = ids

    async def execute(self, command: RegisterUserCommand) -> RegisteredUser:
        # 驗證在開交易之前:輸入不合法時不該佔用資料庫連線
        email = Email.parse(command.email)
        password = RawPassword.parse(command.password)

        user = User.register(
            id=self.ids.new_id(),
            email=email,
            password=password,
            hasher=self.hasher,
            now=self.clock.now(),
        )

        async with self.uow:
            # 唯一性由 add() 背後的約束保證,不先查再寫(§2.2 的競態)
            await self.uow.users.add(user)
            await self.uow.commit()

        return RegisteredUser(user_id=user.id, email=user.email.value)
