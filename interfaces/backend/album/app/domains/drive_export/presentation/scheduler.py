"""ExportScheduler 的實作:FastAPI background task。

放在 presentation 而不是 infrastructure,因為它依賴 FastAPI 的 BackgroundTasks,
而 infrastructure 不可以依賴 HTTP 框架(分層規則 3)。

背景任務**不能**沿用請求的 DB session——回應送出後那個 session 就關了,所以這裡
接受一個「每次執行都重新組裝 use case」的工廠。
"""

from collections.abc import Callable

from fastapi import BackgroundTasks

from app.domains.drive_export.application.dtos import ExportJob
from app.domains.drive_export.application.ports import ExportScheduler
from app.domains.drive_export.application.use_cases.run_export import RunExport


class BackgroundTaskExportScheduler(ExportScheduler):
    def __init__(
        self, background_tasks: BackgroundTasks, run_export_factory: Callable[[], RunExport]
    ) -> None:
        self._background_tasks = background_tasks
        self._run_export_factory = run_export_factory

    def schedule(self, job: ExportJob) -> None:
        self._background_tasks.add_task(self._run, job)

    async def _run(self, job: ExportJob) -> None:
        await self._run_export_factory().execute(job)
