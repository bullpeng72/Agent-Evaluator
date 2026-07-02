# SPEC-008: Compliance 프레임워크 확장 (SOC2/PCI-DSS)

**Phase:** P3 · **상태:** Draft · **의존성:** 없음

## Context

- `agent_evaluator/helpers/taskresult_helpers.py:3672-3679`에서 `ComplianceConfig.compliance_framework`가 `"hipaa"`인 경우에만 고정 키워드 리스트(`patient, diagnosis, treatment, medical record, 환자, 진단, 치료`)로 `hipaa:phi_exposure`를 판정하고, `"gdpr"`인 경우 PII 카테고리 2개 이상 동시 검출 시 `gdpr:pii_combination`을 판정한다.
- `"pci_dss"`, `"soc2"` 등 다른 값은 별도 분기가 없어 generic PII 스캔만 적용된다(2026-07-02 세션에서 직접 확인). `:2073`에 "PCI DSS" 언급이 있으나 이는 `credit_card_leak` CVSS 가중치(4.5)에 대한 **주석**일 뿐, `eval_compliance`의 실제 프레임워크 분기 로직이 아니다.
- CLAUDE.md 등 프로젝트 문서에서 규제 프레임워크를 이름으로 언급하는 것과 실제 구현 사이 괴리가 있다.

## Goals

- SOC2/PCI-DSS를 HIPAA/GDPR과 동등한 수준(프레임워크별 최소 키워드/패턴 룰셋)으로 지원한다.
- 지원되지 않는 프레임워크 값을 지정했을 때 조용히 generic 처리되지 않고 사용자에게 명시적으로 알린다.

## Non-Goals

- 완전한 법률 자문 수준의 규정 준수 판정 — 이번 스펙은 키워드/패턴 기반 휴리스틱 확장에 한정한다.
- 프레임워크별 세부 조항(예: PCI-DSS 12개 요구사항 전체) 매핑 — 최소 실용 룰셋만 다룬다.

## Requirements

- **REQ-1**: `ComplianceConfig.compliance_framework`에 `"pci_dss"` 값을 추가하고, 카드 소지자 데이터(PAN, CVV, 만료일 등) 관련 키워드/패턴이 응답에 노출되면 `pci_dss:cardholder_data_exposure`를 판정한다. 기존 `credit_card_leak` 정규식(`taskresult_helpers.py:92` 부근)을 재사용한다.
- **REQ-2**: `"soc2"` 값을 추가하고, 최소 침해 지표(예: 접근 통제 우회 시도 키워드, 미인가 데이터 이동 관련 표현)가 감지되면 `soc2:trust_service_violation`을 판정한다.
- **REQ-3**: `compliance_framework`가 위 4개 값(`hipaa`/`gdpr`/`pci_dss`/`soc2`) 중 하나가 아니면서 `"general"`도 아닌 경우, `ComplianceConfig.__post_init__`에서 `UserWarning`을 발생시켜 "미지원 프레임워크 값 — generic PII 스캔만 적용됨"을 명시한다(기존에는 조용히 generic 처리).
- **REQ-4**: 각 프레임워크 위반 유형에 대한 심각도 가중치(`taskresult_helpers.py:3683-3684`의 `hipaa: 0.40`, `gdpr: 0.35` 패턴과 동등한 형식)를 `pci_dss`, `soc2`에도 정의한다.

## Interface

```python
# 변경 전
ComplianceConfig(compliance_framework="pci_dss")  # 조용히 generic 처리됨

# 변경 후 (하위호환 — 새 값 지원 추가, 기존 값 동작 불변)
ComplianceConfig(compliance_framework="pci_dss")  # REQ-1 룰셋 적용
ComplianceConfig(compliance_framework="unknown_fw")  # REQ-3: UserWarning 발생, generic 처리는 유지
```

## Acceptance

- `hipaa`/`gdpr`/`pci_dss`/`soc2` 4개 프레임워크 각각 최소 1개 위반 탐지 테스트(각 프레임워크 특화 키워드/패턴이 포함된 응답 픽스처 사용).
- 미지원 프레임워크 값 지정 시 `UserWarning` 발생 및 기존 generic 처리 결과가 유지되는지 검증.
- 기존 `hipaa`/`gdpr` 테스트 결과가 이번 변경으로 달라지지 않는지 회귀 검증.

## Compatibility

- 기존 `"hipaa"`/`"gdpr"`/`"general"` 동작은 변경 없음. `"pci_dss"`/`"soc2"`는 이전에 조용히 generic 처리되던 것이 이제 프레임워크 특화 처리로 바뀌므로, 해당 값을 이미 사용 중인 사용자가 있다면 판정 결과가 달라질 수 있음(생김새는 additive이지만 동작은 변경) — CHANGELOG에 명시.

## Rollout

1. PCI-DSS 룰셋 구현(REQ-1) — 기존 `credit_card_leak` 정규식 재사용.
2. SOC2 룰셋 구현(REQ-2) — 최소 키워드셋으로 시작, 추후 확장 여지 문서화.
3. `__post_init__` 경고 추가(REQ-3).
4. 문서(`Docs/02_METRICS_GUIDE.md` 등)에 지원 프레임워크 목록과 한계(법률 자문 아님) 명시.

## Risks

- `"pci_dss"`/`"soc2"`를 이미 지정해 쓰던 기존 사용자가 있다면(가능성 낮음, 기존엔 generic 처리라 사실상 미지원이었음) 이번 변경으로 위반 판정이 새로 발생할 수 있음 → 마이너 버전 릴리스 노트에 "이전에 이 값들은 generic 처리였고, 이제 프레임워크 특화 룰셋이 적용됩니다"를 명확히 기술.
