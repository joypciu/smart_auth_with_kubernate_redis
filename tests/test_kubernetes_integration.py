from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def _find_powershell() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


@pytest.mark.skipif(shutil.which("kubectl") is None, reason="kubectl is required for Kubernetes integration rendering")
@pytest.mark.skipif(_find_powershell() is None, reason="PowerShell is required for overlay env export")
def test_local_kubernetes_overlay_renders_from_generated_env(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parent.parent
    temp_root = tmp_path / "project"

    shutil.copytree(project_root / "k8s", temp_root / "k8s")
    (temp_root / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy2(project_root / "scripts" / "export-k8s-overlay-env.ps1", temp_root / "scripts" / "export-k8s-overlay-env.ps1")

    env_file = temp_root / ".env"
    env_file.write_text(
        "\n".join(
            [
                "APP_NAME=Smart Auth API",
                "API_V1_PREFIX=/api/v1",
                "LOG_LEVEL=INFO",
                "ACCESS_TOKEN_EXPIRE_MINUTES=15",
                "REFRESH_TOKEN_EXPIRE_DAYS=7",
                "POSTGRES_DB=smart_auth",
                "POSTGRES_USER=postgres",
                "POSTGRES_PASSWORD=supersecret123",
                "SECRET_KEY=super-secret-key-for-k8s-render-validation-0123456789abcdef",
                "RATE_LIMIT_AUTH_REQUESTS=5",
                "RATE_LIMIT_AUTH_WINDOW_SECONDS=60",
                "GOOGLE_CLIENT_ID=",
                "GOOGLE_CLIENT_SECRET=",
                "GITHUB_CLIENT_ID=",
                "GITHUB_CLIENT_SECRET=",
            ]
        ),
        encoding="utf-8",
    )

    powershell = _find_powershell()
    assert powershell is not None

    export_result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(temp_root / "scripts" / "export-k8s-overlay-env.ps1"),
            "-Overlay",
            "local",
            "-EnvPath",
            str(env_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert export_result.returncode == 0, export_result.stderr or export_result.stdout

    config_env = temp_root / "k8s" / "overlays" / "local" / "config.env"
    secrets_env = temp_root / "k8s" / "overlays" / "local" / "secrets.env"
    assert config_env.exists()
    assert secrets_env.exists()

    render_result = subprocess.run(
        ["kubectl", "kustomize", str(temp_root / "k8s" / "overlays" / "local")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert render_result.returncode == 0, render_result.stderr or render_result.stdout
    assert "kind: Namespace" in render_result.stdout
    assert "kind: ConfigMap" in render_result.stdout
    assert "kind: Secret" in render_result.stdout
    assert "kind: Deployment" in render_result.stdout
    assert "kind: StatefulSet" in render_result.stdout
    assert "name: smart-auth-api" in render_result.stdout