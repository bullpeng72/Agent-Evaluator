# /content — 일별 통합 콘텐츠 생성

`day_plan.json`을 읽어 하루치 블로그 + YouTube 콘텐츠를 자동으로 생성한다.

## 사용법

```
/content --day_01              # day_01 블로그 + YouTube 나레이션 생성
/content --day_01 --force      # 기존 파일 덮어쓰기
/content --day_01 --blog-only  # 블로그만
/content --day_01 --youtube-only  # YouTube만
/content --list                # 30일 전체 계획 + 생성 현황 출력
/content --day_01 --status     # 해당 day 현황 확인
```

## 실행 절차

인자: $ARGUMENTS

### 1단계: 인자 파싱

`$ARGUMENTS`에서 day 번호를 추출한다.

- `--list` → `python Content/pipeline/run_day.py --list` 실행 후 종료
- `--day_NN` → NN 추출, 이하 실행
- 숫자만 (`01`, `1`) → `day_01` 형식으로 변환

나머지 옵션 (`--force`, `--blog-only`, `--youtube-only`, `--status`) 은 그대로 전달.

### 2단계: 계획 확인

해당 day의 내용을 `Content/day_plan.json`에서 확인해 출력한다:

```bash
python Content/pipeline/run_day.py <day_key> --status
```

`--status` 단독 인자인 경우 여기서 종료한다.

### 3단계: 콘텐츠 생성

```bash
python Content/pipeline/run_day.py <day_key> [--force] [--blog-only] [--youtube-only] --skip-audio
```

`--skip-audio`는 항상 포함한다 (TTS 없이 실행).

### 4단계: 생성 결과 확인

블로그가 생성된 경우 앞부분을 출력한다:
```bash
for post_id in <blog_ids>:
    head -30 Content/Blog/output/<post_id>/post_velog.md 2>/dev/null
```

YouTube 나레이션이 생성된 경우 앞부분을 출력한다:
```bash
for episode_id in <youtube_ids>:
    head -40 Content/YouTube/output/<episode_id>/narration.md 2>/dev/null
```

### 5단계: 다음 단계 안내

**블로그 발행** (생성된 포스트가 있는 경우):
```
생성된 포스트를 Velog에 발행하려면:
  /blog <post_id> --publish
```

**YouTube 파이프라인 완성** (나레이션이 생성된 경우):
```
나레이션을 검토 후 슬라이드·자막·메타데이터를 생성하려면:
  /youtube <episode_id> --force --skip-audio
```

**출판 단계** (해당 day에 publish 항목이 있는 경우):
```
출판은 수동 실행이 필요합니다:
  /publish --platform bookk
  /publish --platform kdp-en
```
