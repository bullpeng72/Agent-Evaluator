"""
tests/test_dashboard_auth.py
=============================
SPEC-005: 대시보드 인증 미들웨어 (옵트인) 검증.
"""
from __future__ import annotations

from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

_TOKEN = "test-secret-token"


@pytest.fixture(scope="module")
def results_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("results")


@pytest.fixture(scope="module")
def client_no_auth(results_dir: Path) -> TestClient:
    from agent_evaluator.serve.server import create_app
    app = create_app(results_dir=results_dir, watch=False, offline=False)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def client_auth(results_dir: Path) -> TestClient:
    from agent_evaluator.serve.server import create_app
    app = create_app(results_dir=results_dir, watch=False, offline=False, auth_token=_TOKEN)
    return TestClient(app, raise_server_exceptions=False)


class TestNoAuthBackwardCompatible:
    """REQ-2/REQ-3: auth_token 미지정 시 기존 동작(무인증) 그대로."""

    def test_root_accessible_without_token(self, client_no_auth: TestClient):
        resp = client_no_auth.get("/")
        assert resp.status_code == 200

    def test_api_route_accessible_without_token(self, client_no_auth: TestClient):
        resp = client_no_auth.get("/api/data/results")
        assert resp.status_code != 401

    def test_api_docs_accessible_without_token(self, client_no_auth: TestClient):
        resp = client_no_auth.get("/api/docs")
        assert resp.status_code == 200


class TestAuthEnabledBlocksUnauthenticated:
    """REQ-1/REQ-3/REQ-4: 토큰 설정 시 전 라우트(문서 포함) 인증 필요."""

    def test_root_without_token_redirects_to_login(self, client_auth: TestClient):
        resp = client_auth.get("/", headers={"accept": "text/html"}, follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert resp.headers["location"].startswith("/login")

    def test_api_route_without_token_returns_401(self, client_auth: TestClient):
        resp = client_auth.get("/api/data/results", headers={"accept": "application/json"})
        assert resp.status_code == 401
        assert "token" not in resp.text.lower()  # REQ-4: 토큰 힌트 노출 금지

    def test_api_docs_without_token_returns_401(self, client_auth: TestClient):
        resp = client_auth.get("/api/docs", headers={"accept": "application/json"})
        assert resp.status_code == 401

    def test_wrong_bearer_token_returns_401(self, client_auth: TestClient):
        resp = client_auth.get(
            "/api/data/results",
            headers={"accept": "application/json", "authorization": "Bearer wrong-token"},
        )
        assert resp.status_code == 401


class TestAuthEnabledAllowsValidToken:
    """REQ-3: 올바른 Bearer 토큰이면 통과."""

    def test_correct_bearer_token_returns_200(self, client_auth: TestClient):
        resp = client_auth.get(
            "/api/data/results",
            headers={"authorization": f"Bearer {_TOKEN}"},
        )
        assert resp.status_code != 401

    def test_login_page_accessible_without_token(self, client_auth: TestClient):
        resp = client_auth.get("/login")
        assert resp.status_code == 200
        assert "token" in resp.text.lower()

    def test_login_with_correct_token_sets_cookie_and_redirects(self, client_auth: TestClient):
        resp = client_auth.post(
            "/login", data={"token": _TOKEN, "next": "/"}, follow_redirects=False
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"
        assert "ae_auth" in resp.cookies

    def test_login_with_wrong_token_redirects_with_error(self, client_auth: TestClient):
        resp = client_auth.post(
            "/login", data={"token": "wrong", "next": "/"}, follow_redirects=False
        )
        assert resp.status_code == 303
        assert "error=1" in resp.headers["location"]

    def test_cookie_grants_access_after_login(self, client_auth: TestClient):
        login_resp = client_auth.post(
            "/login", data={"token": _TOKEN, "next": "/"}, follow_redirects=False
        )
        cookie_value = login_resp.cookies["ae_auth"]
        client_auth.cookies.set("ae_auth", cookie_value)
        try:
            resp = client_auth.get("/", headers={"accept": "text/html"})
            assert resp.status_code == 200
        finally:
            client_auth.cookies.clear()
