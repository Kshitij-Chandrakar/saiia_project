"""The supported runtime has one manifest covering its direct Python imports."""
import ast
from pathlib import Path
import sys

import pytest

from packaging.requirements import Requirement


ROOT = Path(__file__).resolve().parents[2]
IMPORT_DISTRIBUTIONS = {
    "PIL": "pillow", "docx": "python-docx", "dotenv": "python-dotenv",
    "fitz": "pymupdf", "google": "protobuf", "grpc": "grpcio", "jwt": "pyjwt",
    "pyaudiowpatch": "pyaudiowpatch", "rapidocr_onnxruntime": "rapidocr-onnxruntime",
    "whisper": "openai-whisper",
}


def test_single_runtime_manifest_covers_application_imports():
    assert not (ROOT / "backend/requirements.txt").exists()
    assert not (ROOT / "frontend/requirements.txt").exists()
    requirements = [Requirement(line) for raw in (ROOT / "requirements.txt").read_text().splitlines()
                    if (line := raw.strip()) and not line.startswith("#")]
    names = [r.name.lower().replace("_", "-") for r in requirements]
    assert len(names) == len(set(names)), "Duplicate runtime requirement"
    assert all(r.url or list(r.specifier) for r in requirements), "Pin direct runtime dependencies"
    missing = set()
    for source in (ROOT / "backend/app").rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8-sig"))):
            imports = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                       else [node.module] if isinstance(node, ast.ImportFrom) and node.module and not node.level else [])
            for module in imports:
                name = module.split(".")[0]
                if name in sys.stdlib_module_names or name == "app":
                    continue
                distribution = IMPORT_DISTRIBUTIONS.get(name, name).lower().replace("_", "-")
                if distribution not in names:
                    missing.add((module, str(source.relative_to(ROOT))))
    assert not missing, f"Unclassified runtime imports: {sorted(missing)}"


@pytest.mark.parametrize("exit_code", [0, 7])
def test_setup_preserves_native_exit_status_with_stderr(tmp_path, exit_code):
    import os
    import shutil
    import subprocess
    shell = shutil.which("powershell.exe") or shutil.which("pwsh")
    if not shell:
        pytest.skip("PowerShell required for setup wrapper regression")
    quote = lambda text: "'" + str(text).replace("'", "''") + "'"
    driver = tmp_path / "driver.ps1"
    driver.write_text(
        "$ErrorActionPreference='Stop'\n"
        f"$ast=[scriptblock]::Create((Get-Content -LiteralPath {quote(ROOT / 'scripts/setup-dev.ps1')} -Raw)).Ast\n"
        "$definition=$ast.Find({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Invoke-SetupCommand'},$true)\n"
        ". ([scriptblock]::Create($definition.Extent.Text))\n"
        "$caught=$false\n"
        f"try {{ Invoke-SetupCommand {quote(sys.executable)} @('-c','import sys; sys.stderr.write(chr(120)); sys.exit({exit_code})') }} catch {{ $caught=$true }}\n"
        f"if ($caught -ne ${str(bool(exit_code)).lower()}) {{ exit 1 }}\n"
        "Write-Output 'EXIT_STATUS_VERIFIED'\n"
    )
    environment = dict(os.environ)
    if os.name == "nt":
        import ctypes
        windows = ctypes.create_unicode_buffer(32768)
        assert ctypes.windll.kernel32.GetWindowsDirectoryW(windows, len(windows))
        environment.update(SystemRoot=windows.value, SystemDrive=Path(windows.value).drive, PATHEXT=".EXE")
    result = subprocess.run([shell, "-NoProfile", "-File", str(driver)], env=environment,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0 and "EXIT_STATUS_VERIFIED" in result.stdout, result.stdout + result.stderr
