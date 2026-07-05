# 도서 이미지 삽입 가이드

`build_book.py`(단일 HTML)와 `build_pdf_chapters.py`(챕터별 PDF) 양쪽에서
외부 이미지를 올바르게 포함하는 방법을 정리한다.

---

## 1. 디렉토리 구조 규칙

이미지는 **마크다운 파일과 같은 Part 디렉토리** 안의 `images/` 폴더에 배치한다.

```
Book/
├── Part_II_지표시스템/
│   ├── Chapter_03_Harness_Engineering_기초.md
│   └── images/
│       ├── ch03_terminal.png       ← 터미널 실행 결과
│       └── ch03_dashboard.png      ← 대시보드 화면
├── Part_I_기초/
│   ├── Chapter_01_AI에이전트_평가란_무엇인가.md
│   └── images/
│       └── ch01_architecture.png
```

> 파일명은 `ch{챕터번호}_{설명}.png` 형식을 권장한다.

---

## 2. 기본 이미지 삽입

마크다운 표준 문법을 사용한다. 경로는 **마크다운 파일 기준 상대 경로**로 작성한다.

```markdown
![그림 3.1 — 터미널 실행 결과](./images/ch03_terminal.png)
```

- 빌드 시 경로가 자동 변환되므로 `./images/...` 형식 그대로 유지한다.
- `alt` 텍스트(`그림 3.1 — ...`)는 PDF 접근성과 빌드 오류 디버깅에 활용된다.

---

## 3. 캡션이 있는 figure 삽입

캡션(`figcaption`)이 필요하면 `@@HTML_START@@ / @@HTML_END@@` 블록 안에
표준 HTML `<figure>` 태그를 사용한다.

```markdown
@@HTML_START@@
<figure>
  <img src="./images/ch03_dashboard.png" alt="Harness Gate 대시보드">
  <figcaption>그림 3.2 — Harness Gate 대시보드 실행 화면</figcaption>
</figure>
@@HTML_END@@
```

캡션 없이 중앙 정렬만 필요한 경우에도 `<figure>` 래핑으로 간단히 처리할 수 있다.

---

## 4. 권장 이미지 사양

| 항목 | 권장값 | 이유 |
|------|--------|------|
| 형식 | PNG | 텍스트·UI 화면의 선명도 유지 |
| 폭 | 800–1200 px | A4 본문 폭(624 px) 기준 1–2× |
| 해상도 | 96–144 dpi | Playwright PDF 출력 최적화 |
| 배경 | 흰색 또는 불투명 | PDF에서 투명 배경이 검게 렌더될 수 있음 |

> 이미지 폭이 본문 폭(624 px)을 초과해도 JS가 비율을 유지하며 자동 축소한다.

---

## 5. 빌드별 경로 처리 방식

빌드 스크립트가 `src` 경로를 자동으로 변환하므로 마크다운 작성자는
항상 `./images/...` 상대 경로만 사용하면 된다.

| 빌드 | 변환 함수 | 변환 결과 예시 |
|------|-----------|---------------|
| `build_book.py` (HTML) | `_rewrite_img_paths_for_book` | `Part_II_지표시스템/images/ch03_dashboard.png` |
| `build_pdf_chapters.py` (PDF) | `_rewrite_img_paths` | `file:///절대경로/Part_II_지표시스템/images/ch03_dashboard.png` |

---

## 6. 자동 크기 조정 동작

### HTML (`build_book.py`)
CSS만으로 처리된다.

```css
img { max-width: 100%; height: auto; display: block; margin: 12px auto; }
```

### PDF (`build_pdf_chapters.py`)
CSS 외에 JS가 `naturalWidth`를 측정해 `width`/`height` attribute를 직접 재지정한다.
Chrome PDF 엔진이 attribute 값을 intrinsic size로 사용하기 때문이다.

```javascript
if (iw > 0 && iw > availW) {
  img.setAttribute('width',  Math.round(availW));        // 본문 폭(624px)으로 축소
  img.setAttribute('height', Math.round(ih * availW / iw)); // 비율 유지
}
```

---

## 7. 체크리스트

이미지를 추가할 때 확인할 사항:

- [ ] `Part_XX_.../images/` 디렉토리에 파일 배치
- [ ] 마크다운에서 `./images/파일명.png` 상대 경로 사용
- [ ] PNG 권장, 배경 불투명
- [ ] `build_book.py` 빌드 후 브라우저에서 이미지 표시 확인
- [ ] `build_pdf_chapters.py` 빌드 후 PDF에서 이미지 위치·크기 확인
