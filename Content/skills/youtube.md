# /youtube — YouTube 콘텐츠 파이프라인

YouTube 에피소드를 생성한다. 챕터 → 나레이션 → 슬라이드 → 음성 → 자막 → 메타데이터 순으로 실행한다.

## 사용법

```
/youtube <episode_id> [옵션]
/youtube --list
/youtube --season <N>
```

**episode_id 예시**: S1E1, S2E3, S6E5, F1, R3  
**옵션**: `--skip-audio` (음성 생략) · `--pdf` (슬라이드 PDF) · `--force` (덮어쓰기)

## 실행 절차

인자: $ARGUMENTS

다음 순서로 실행한다.

### 1단계: 사전 점검

`Content/YouTube/pipeline/` 경로에서 아래를 확인한다.

```bash
cd Content/YouTube/pipeline
python -c "import anthropic; print('anthropic OK')" 2>&1
```

`.env`에서 `ANTHROPIC_API_KEY` 설정 여부를 확인한다:
```bash
grep -q "ANTHROPIC_API_KEY" ../../../../.env 2>/dev/null && echo "API키 설정됨" || echo "⚠️  ANTHROPIC_API_KEY 미설정"
```

TTS 관련 환경변수도 확인한다:
```bash
grep "TTS_PROVIDER\|ELEVENLABS\|CLOVA" ../../../../.env 2>/dev/null || echo "TTS 미설정 (--skip-audio 권장)"
```

### 2단계: 인자 분기

`$ARGUMENTS`가 `--list`이면:
```bash
cd Content/YouTube/pipeline && python run_all.py --list
```

`$ARGUMENTS`가 `--season N`이면:
```bash
cd Content/YouTube/pipeline && python run_all.py $ARGUMENTS --skip-audio
```

그 외(에피소드 ID 지정)이면 아래 3~5단계를 진행한다.

### 3단계: 나레이션 생성 (Step 1만 먼저 실행)

```bash
cd Content/YouTube/pipeline && python chapter_to_narration.py $ARGUMENTS 2>&1
```

생성된 나레이션 파일을 읽어 앞부분(200줄)을 출력해 저자가 검토할 수 있게 한다:
```bash
head -200 Content/YouTube/output/<episode_id>/narration.md 2>/dev/null
```

나레이션 검토 안내를 출력한다:
> **검토 필요**: `Content/YouTube/output/<episode_id>/narration.md` 파일을 확인하고 기술 오류나 어색한 표현을 수정하세요.  
> 수정 완료 후 `/youtube <episode_id> --force [--skip-audio]`로 나머지 단계를 실행하세요.

`--force` 옵션이 포함된 경우에는 검토 단계를 건너뛰고 4단계로 진행한다.

### 4단계: 나머지 파이프라인 (--force 포함 시)

```bash
cd Content/YouTube/pipeline && python narration_to_slides.py <episode_id> 2>&1
cd Content/YouTube/pipeline && python narration_to_audio.py <episode_id> 2>&1   # --skip-audio 없을 때
cd Content/YouTube/pipeline && python narration_to_srt.py <episode_id> 2>&1
cd Content/YouTube/pipeline && python generate_metadata.py <episode_id> 2>&1
```

### 5단계: 결과 요약

`Content/YouTube/output/<episode_id>/` 디렉토리의 파일 목록과 크기를 출력한다:
```bash
ls -lh Content/YouTube/output/<episode_id>/ 2>/dev/null
```

metadata.txt 파일이 있으면 내용을 출력한다:
```bash
cat Content/YouTube/output/<episode_id>/metadata.txt 2>/dev/null
```

다음 단계를 안내한다:
- 슬라이드: `Content/YouTube/output/<episode_id>/slides.md`
- 음성: `Content/YouTube/output/<episode_id>/narration.mp3`
- 자막: `Content/YouTube/output/<episode_id>/narration.srt`
- YouTube 업로드: `metadata.txt`에서 제목·설명·태그 복사
