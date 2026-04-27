# /blog — 블로그 포스트 파이프라인 (Velog 전용)

책 챕터를 Velog용 블로그 포스트로 변환하고 SEO 메타데이터를 생성한다.
`--publish` 옵션을 추가하면 Velog에 자동 발행한다.

## 사용법

```
/blog <post_id> [--skip-seo] [--force]
/blog <post_id> --publish          # 포스트 생성 + Velog 자동 발행
/blog <post_id> --publish --draft  # 포스트 생성 + Velog 임시저장
/blog --list
/blog --all [--type 튜토리얼|개념|심층분석|사례연구]
```

**post_id 예시**: gate_a, gate_b, quickstart, retrofit_30min, failure_loop  
**Velog 발행 인증**: `.env`의 `VELOG_ACCESS_TOKEN` (브라우저 F12 → Application → Cookies → velog.io)

## 실행 절차

인자: $ARGUMENTS

### 1단계: 사전 점검

```bash
python -c "import anthropic; print('anthropic OK')" 2>&1
grep -q "ANTHROPIC_API_KEY" .env 2>/dev/null && echo "API키 설정됨" || echo "⚠️  ANTHROPIC_API_KEY 미설정"
```

`--publish`가 포함된 경우 Velog 토큰도 확인한다:
```bash
grep -q "VELOG_ACCESS_TOKEN" .env 2>/dev/null && echo "Velog 토큰 설정됨" || echo "⚠️  VELOG_ACCESS_TOKEN 미설정"
```

### 2단계: 인자 분기

`$ARGUMENTS`가 `--list`이면:
```bash
cd Media/Content/Blog/pipeline && python run_all.py --list
```

`$ARGUMENTS`가 `--all`이면:
```bash
cd Media/Content/Blog/pipeline && python run_all.py $ARGUMENTS 2>&1
```

그 외(post_id 지정)이면 아래 3~5단계를 진행한다.

### 3단계: 포스트 생성

post_id만 추출해서 실행한다 (--publish, --draft 플래그는 제외):
```bash
cd Media/Content/Blog/pipeline && python run_all.py <post_id> [--force] 2>&1
```

### 4단계: 결과 요약

생성된 포스트 파일을 확인하고 앞부분(60줄)을 출력한다:
```bash
head -60 Media/Content/Blog/output/<post_id>/post_velog.md 2>/dev/null
```

SEO 결과를 출력한다:
```bash
cat Media/Content/Blog/output/<post_id>/seo.txt 2>/dev/null
```

파일 목록과 크기를 출력한다:
```bash
ls -lh Media/Content/Blog/output/<post_id>/ 2>/dev/null
```

### 5단계: Velog 자동 발행 (`--publish` 포함 시)

`$ARGUMENTS`에 `--publish`가 있으면 아래를 실행한다.

`--draft`도 포함된 경우:
```bash
cd Media/Content/Blog/pipeline && python publish_to_velog.py <post_id> --draft 2>&1
```

`--draft` 없는 경우 (즉시 발행):
```bash
cd Media/Content/Blog/pipeline && python publish_to_velog.py <post_id> 2>&1
```

발행 성공 시 반환된 URL을 사용자에게 출력한다.

`VELOG_ACCESS_TOKEN`이 없으면 아래 안내를 출력하고 중단한다:
```
VELOG_ACCESS_TOKEN이 필요합니다.
Chrome F12 → Application → Cookies → velog.io → access_token 값 복사 후:
echo "VELOG_ACCESS_TOKEN=복사한값" >> .env
```

`--publish`가 없는 경우 다음 게시 안내를 출력한다:
- **Velog 수동**: `Media/Content/Blog/output/<post_id>/post_velog.md` 내용을 Velog 에디터에 붙여넣기
- **Velog 자동**: `/blog <post_id> --publish`
- **SEO**: `seo.txt`의 meta_description을 포스트 설명란에 입력
