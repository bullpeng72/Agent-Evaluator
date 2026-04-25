# /blog — 블로그 포스트 파이프라인

책 챕터를 Velog·Tistory·Medium용 블로그 포스트로 변환하고 SEO 메타데이터를 생성한다.

## 사용법

```
/blog <post_id> [--platform velog|tistory|medium|all] [--skip-seo] [--force]
/blog --list
/blog --all [--type 튜토리얼|개념|심층분석|사례연구]
```

**post_id 예시**: gate_a, gate_b, quickstart, retrofit_30min, failure_loop  
**플랫폼 기본값**: velog

## 실행 절차

인자: $ARGUMENTS

### 1단계: 사전 점검

```bash
python -c "import anthropic; print('anthropic OK')" 2>&1
grep -q "ANTHROPIC_API_KEY" .env 2>/dev/null && echo "API키 설정됨" || echo "⚠️  ANTHROPIC_API_KEY 미설정"
```

### 2단계: 인자 분기

`$ARGUMENTS`가 `--list`이면:
```bash
cd Content/Blog/pipeline && python run_all.py --list
```

`$ARGUMENTS`가 `--all`이면:
```bash
cd Content/Blog/pipeline && python run_all.py $ARGUMENTS 2>&1
```

그 외(post_id 지정)이면 아래 3~4단계를 진행한다.

### 3단계: 포스트 생성

```bash
cd Content/Blog/pipeline && python run_all.py $ARGUMENTS 2>&1
```

### 4단계: 결과 요약

생성된 포스트 파일을 확인하고 앞부분(60줄)을 출력한다:
```bash
head -60 Content/Blog/output/<post_id>/post_velog.md 2>/dev/null
```

SEO 결과를 출력한다:
```bash
cat Content/Blog/output/<post_id>/seo.txt 2>/dev/null
```

파일 목록과 크기를 출력한다:
```bash
ls -lh Content/Blog/output/<post_id>/ 2>/dev/null
```

다음 게시 안내를 출력한다:
- **Velog**: `post_velog.md` 내용을 Velog 에디터에 붙여넣기
- **Tistory**: `post_tistory.md` → HTML 모드로 게시
- **Medium**: `post_medium.md` → Medium Import Story 기능 사용
- **SEO**: `seo.txt`의 meta_description을 포스트 설명란에 입력
