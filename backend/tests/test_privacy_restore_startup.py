"""Execute the actual isolated lifespan quarantine branch without dotenv/services."""

import ast
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.concurrency import run_in_threadpool


@pytest.mark.parametrize("coordinator", [None, SimpleNamespace(ready=lambda: False)])
def test_required_restore_boot_starts_no_background_services(coordinator):
    source = Path(__file__).parents[1] / "app/main.py"
    node = next(
        n
        for n in ast.parse(source.read_text(encoding="utf-8")).body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "lifespan"
    )
    namespace = {
        "asynccontextmanager": asynccontextmanager,
        "settings": SimpleNamespace(C15_RESTORE_BOOT_REQUIRED="true"),
        "run_in_threadpool": run_in_threadpool,
    }
    exec(  # noqa: S102 -- execute only the inspected repository lifespan AST
        compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"),
        namespace,
    )
    app = SimpleNamespace(state=SimpleNamespace(restore_coordinator=coordinator))

    async def run():
        async with namespace["lifespan"](app):
            assert vars(app.state) == {
                "restore_coordinator": coordinator,
                "restore_startup_ready": False,
            }

    asyncio.run(run())
