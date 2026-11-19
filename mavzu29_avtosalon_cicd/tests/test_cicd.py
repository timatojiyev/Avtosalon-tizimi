"""“Pipeline as code” testlari: workflow va deploy fayllari to'g'ri tuzilganini tekshiradi."""
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")
ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text())


def test_ci_pipeline_order():
    ci = load("ci.yml")
    assert list(ci["jobs"]) == ["lint", "test", "integration"]
    assert ci["jobs"]["test"]["needs"] == "lint" and ci["jobs"]["integration"]["needs"] == "test"
    assert ci["jobs"]["test"]["strategy"]["matrix"]["python"] == ["3.11", "3.12"]
    triggers = ci[True] if True in ci else ci["on"]       # YAML'da `on` kaliti True bo'lib o'qiladi
    assert "pull_request" in triggers and "push" in triggers


def test_cd_builds_every_image_and_gates_production():
    cd = load("cd.yml")
    images = {i["image"] for i in cd["jobs"]["build"]["strategy"]["matrix"]["include"]}
    assert images == {"car-service", "customer-service", "sales-service", "financing-service", "notification-worker", "web"}
    for i in cd["jobs"]["build"]["strategy"]["matrix"]["include"]:
        assert (ROOT / i["dockerfile"]).exists()
    assert set(cd["jobs"]["deploy"]["needs"]) == {"prepare", "build", "scan"}       # skanersiz deploy yo'q
    assert "environment" in cd["jobs"]["deploy"]
    assert cd["jobs"]["scan"]["steps"][0]["with"]["exit-code"] == "1"


def test_deploy_scripts_have_rollback():
    deploy = (ROOT / "deploy" / "deploy.sh").read_text()
    assert "set -euo pipefail" in deploy and "rollback" in deploy.lower() and "wait-healthy.sh" in deploy
    assert "SMOKE_READONLY=1" in deploy        # production'da ma'lumot yaratilmaydi


def test_dockerfiles_are_hardened():
    for df in ROOT.glob("**/Dockerfile"):
        text = df.read_text()
        assert "AS builder" in text and "USER app" in text and "HEALTHCHECK" in text, df
        assert "ARG GIT_SHA" in text, df


def test_health_exposes_version(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "1.2.3")
    monkeypatch.setenv("GIT_SHA", "abcdef0123456")
    from car_service.main import create_app
    h = create_app("sqlite:///:memory:").test_client().get("/health").json
    assert h["version"] == "1.2.3" and h["git_sha"] == "abcdef0"
