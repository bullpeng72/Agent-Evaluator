# SPEC-005: 대시보드 인증 미들웨어 (옵트인)

**Phase:** P0 · **상태:** Implemented (2026-07-02) · **의존성:** 없음 (독립 착수 가능)

> **구현 노트 (REQ-5 설계 변경)**: 스펙 초안은 "세션 스토리지 + fetch 패치"를 제안했으나, 실제 구현은 **로그인 성공 시 HttpOnly 쿠키 발급** 방식을 택했다. 근거: (1) 브라우저의 최상위 페이지 탐색(주소창 입력, 새로고침)은 커스텀 헤더를 붙일 수 없어 Bearer-only 설계로는 최초 페이지 진입 자체가 불가능한 닭-달걀 문제가 있었다. (2) 쿠키는 브라우저가 동일 출처 요청(페이지 탐색 + `fetch()` 둘 다)에 자동 첨부하므로, `dashboard.html.j2`/`dashboard2.html.j2`(각 7,079·12,138줄)의 기존 `fetch()` 호출 71건을 전혀 수정하지 않고도 인증이 투명하게 적용된다(두 파일 모두 `credentials: 'omit'` 미사용 확인 완료 — 기본 동작으로 쿠키 자동 전송). `Authorization: Bearer` 헤더 경로는 API/curl 사용을 위해 그대로 유지(Acceptance의 curl 검증 시나리오와 일치). `/login` 라우트는 인증 미들웨어의 유일한 예외(부트스트래핑 목적)로, REQ-3의 "모든 라우트"는 이 1개 경로를 제외한 나머지 전체로 해석한다.

## Context

- `agent_evaluator/serve/server.py:120-127`에 `CORSMiddleware`(주석: "localhost-only (dashboard is never exposed to the public internet)")와 `NoCacheHTMLMiddleware`(`:130-142`)만 존재한다.
- 14개 라우터 파일(`serve/routers/*.py`) 전체에서 `Depends`/`Authorization`/API 키 검증 패턴이 발견되지 않는다 — 103개 라우트 전부 무인증.
- `serve/routers/golden.py:762` 부근에서 폼 필드로 받은 `openai_api_key`를 그대로 외부 API 호출에 사용하는 지점도 확인됨(인증 부재와 별개로, 키 노출 표면이 넓다는 정황).
- 테넌트/사용자 개념이 `serve/` 어디에도 없음 — 단일 사용자·단일 네트워크 신뢰 전제 설계.

## Goals

- 대시보드를 사내망 등 신뢰 경계가 다른 환경에 배포할 때 최소한의 인증 계층을 **옵트인**으로 제공한다.
- 토큰 미설정 시 기존 동작(무인증, localhost 전제)을 그대로 유지한다.

## Non-Goals

- 멀티테넌시/RBAC(역할 기반 접근 제어) — 이번 스펙은 단일 공유 토큰 수준만 다룬다.
- OAuth/SSO 연동.

## Requirements

- **REQ-1**: `agent-eval dashboard --auth-token <token>` CLI 옵션 또는 `AGENT_EVALUATOR_DASHBOARD_TOKEN` 환경 변수로 Bearer 토큰 인증을 옵트인할 수 있다.
- **REQ-2**: 토큰이 설정되지 않으면 기존과 동일하게 무인증으로 동작한다 (완전 하위호환).
- **REQ-3**: 토큰이 설정된 경우, `/api/docs`·`/api/redoc`을 포함한 **모든** 라우트에 동일한 인증 정책이 예외 없이 적용된다.
- **REQ-4**: 인증 실패 시 `401 Unauthorized`를 반환하며, 응답 바디에 토큰 값이나 힌트를 노출하지 않는다.
- **REQ-5**: 대시보드 프론트엔드(Alpine.js 템플릿, `dashboard.html.j2`/`dashboard2.html.j2`)가 토큰을 세션 스토리지 등에 보관하고 모든 API 호출에 `Authorization: Bearer <token>` 헤더를 첨부하도록 수정한다. 토큰 입력 UI(최초 접속 시 프롬프트 등)를 제공한다.

## Interface

```python
# 변경 전
def create_app(results_dir: Path, title: str = "...", watch: bool = False,
                version: str = _VERSION, offline: bool = False) -> FastAPI: ...

# 변경 후 (하위호환 — auth_token 생략 시 기존과 동일)
def create_app(results_dir: Path, title: str = "...", watch: bool = False,
                version: str = _VERSION, offline: bool = False,
                auth_token: Optional[str] = None) -> FastAPI: ...
```

`auth_token`이 `None`이면 인증 미들웨어 자체를 등록하지 않아 기존 동작과 완전히 동일하다.

## Acceptance

- `auth_token` 미설정 시 기존 대시보드 통합 테스트 전량 통과(무인증 동작 회귀 없음).
- `auth_token` 설정 시: 토큰 없이 요청 → 401, 잘못된 토큰 → 401, 올바른 `Authorization: Bearer` 헤더 포함 요청 → 200 (curl 기반 검증).
- `/api/docs` 등 문서 라우트도 동일하게 401 처리되는지 검증.

## Compatibility

- 완전 하위호환(옵트인) — 기본 배포 시나리오(로컬 개발) 영향 없음.

## Rollout

1. FastAPI 미들웨어로 Bearer 토큰 검증 구현, `auth_token=None`일 때 미들웨어 미등록.
2. CLI(`cli/main.py` `dashboard` 서브커맨드)에 `--auth-token` 옵션 추가.
3. 프론트엔드 템플릿에 토큰 입력/저장/첨부 로직 추가.
4. `Docs/07_OPERATIONS.md`에 "리버스 프록시 뒤 배포 시 --auth-token 필수 권장" 가이드 추가.

## Risks

- 프론트엔드가 토큰을 모든 API 호출에 첨부하도록 빠짐없이 수정하지 않으면 UI 전체가 401로 깨질 수 있음 → 라우터별 통합 테스트로 커버리지 확보.
- 단일 공유 토큰이라 사용자별 감사 추적은 불가능 — 필요 시 후속 스펙(RBAC)에서 다룬다.
