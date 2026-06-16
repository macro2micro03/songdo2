# PDF 한글 폰트 깨짐 (□) 수정 런북

**대상 증상**: 산출물 PDF에서 한글이 모두 ■/□ 사각형으로 표시됨 (영문/숫자/기호는 정상)

**최초 적용**: 2026-04-27, commit `b983c46`
**관련 회귀 사례**: 2026-05-01 commit `1490c9b` (대규모 통합 작업이 폰트 fix를 덮어씀)

---

## 1. 빠른 진단 (1분)

### 관리자로 로그인 → 헤더 상단 확인
- **`⚠️ 한글 폰트 미등록 — PDF 산출물이 □로 깨질 수 있습니다`** expander가 보이면 → 폰트 등록 실패
- 보이지 않으면 → 폰트 등록은 성공. 다른 원인(예: 폰트 임베드 누락) 의심

### Expander 클릭 시 JSON 정보 의미
```json
{
  "normal_path": null,                    // null이면 일반 폰트 미등록
  "bold_path": null,                      // null이면 볼드 폰트 미등록
  "bundle_dir": "/mount/.../modules/outputs/fonts",
  "bundle_dir_exists": true|false,        // false면 fonts 디렉터리 자체가 없음
  "bundle_dir_contents": ["NanumGothic.ttf", "NanumGothicBold.ttf"],
  "errors": []                            // 등록 시도 중 발생한 예외 목록
}
```

| 진단 결과 | 원인 | 조치 |
|----------|------|------|
| `bundle_dir_exists: false` | 폰트 디렉터리 자체가 누락 | 섹션 3 "폰트 파일 복구" |
| `bundle_dir_contents: []` 또는 .ttf 없음 | 디렉터리는 있으나 파일 누락 | 섹션 3 |
| `errors`에 `file too small` | 폰트 파일 손상 (보통 100KB 미만) | 섹션 3 |
| `errors`에 `register(...): ...` | reportlab이 TTF 파싱 실패 | 폰트 재다운로드 (섹션 3) |
| 모두 정상이지만 PDF는 깨짐 | 코드가 등록 결과를 사용 안 함 | 섹션 4 "코드 회귀 확인" |

---

## 2. 정상 동작하는 코드 구조 (참고용)

**파일**: `modules/outputs/pdf.py` 상단

핵심 원칙:
1. **번들 폰트(`modules/outputs/fonts/NanumGothic.ttf`)를 candidates 리스트의 0번째**에 둔다 — Linux/Cloud에서 가장 먼저 발견되도록
2. Windows / Linux apt / Noto CJK fallback을 그 뒤에 둔다
3. **`try/except: pass`만 쓰지 않는다** — 등록 실패 시 로그 + 진단 dict에 기록
4. 모듈 레벨 변수 `KOREAN_FONT_REGISTERED`, `KOREAN_FONT_DIAG`를 export하여 헤더가 가시화

**candidates 순서 (절대 바꾸지 말 것)**:
```python
_candidates_normal = [
    os.path.join(_BUNDLE_DIR, "NanumGothic.ttf"),       # 0: 번들 (최우선)
    "C:/Windows/Fonts/malgun.ttf",                      # 1: Windows
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",  # 2: Linux apt nanum
    "/usr/share/fonts/nanum/NanumGothic.ttf",           # 3: Linux RPM nanum
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # 4: Noto fallback
]
```

`pdf.py` 전체 파일은 commit `b983c46` 시점이 정상 baseline.

---

## 3. 폰트 파일 복구

### 시나리오 A: `modules/outputs/fonts/` 폴더가 없음

```bash
cd <worktree-root>
mkdir -p modules/outputs/fonts
```

### 시나리오 B: TTF 파일이 누락 또는 손상

NanumGothic 공식 출처(Google Fonts):
- https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf
- https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf

```powershell
# Windows PowerShell
$dst = "modules/outputs/fonts"
Invoke-WebRequest -Uri "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf" -OutFile "$dst/NanumGothic.ttf"
Invoke-WebRequest -Uri "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf"    -OutFile "$dst/NanumGothicBold.ttf"
```

**파일 크기 검증** — 둘 다 약 2MB여야 정상:
```bash
ls -la modules/outputs/fonts/
# NanumGothic.ttf      ≈ 2,054,744 bytes
# NanumGothicBold.ttf  ≈ 2,073,868 bytes
```

100KB 미만이면 다운로드 실패한 HTML 파일일 가능성. 다시 받으세요.

### 커밋 & 배포

```bash
git add modules/outputs/fonts/
git commit -m "fix(pdf): restore bundled NanumGothic font files"
git push origin master   # Streamlit Cloud 자동 재빌드
```

---

## 4. 코드 회귀 확인 (Refactor 직후 가장 흔한 원인)

대규모 통합/리팩터 commit 직후 한글이 깨졌다면 → 폰트 등록 코드가 단순화되며 번들 경로가 빠진 것이 거의 확실.

### 확인 방법
```bash
# pdf.py 상단 약 30줄 확인
sed -n '1,40p' modules/outputs/pdf.py | grep -E "BUNDLE_DIR|NanumGothic|candidates"
```

다음 키워드가 모두 보여야 정상:
- `_BUNDLE_DIR`
- `NanumGothic.ttf`
- `_candidates_normal` (리스트 형태)
- `KOREAN_FONT_REGISTERED`

하나라도 없으면 → 회귀. 섹션 5의 표준 패치 다시 적용.

---

## 5. 표준 패치 재적용

`pdf.py` 상단 폰트 등록 블록을 commit `b983c46`의 코드로 교체.

**가장 빠른 방법** — 해당 commit에서 직접 복사:
```bash
git show b983c46:modules/outputs/pdf.py | sed -n '1,100p'
```

위 출력에서 `# 한글 폰트 등록 ...` 블록을 현재 `pdf.py`의 동일 위치에 붙여넣기.

또는 **체리픽**:
```bash
git checkout b983c46 -- modules/outputs/pdf.py core/header.py
# (다른 변경 사항이 함께 들어올 수 있으니 diff 확인 후 commit)
```

---

## 6. 배포 정보

| 항목 | 값 |
|------|----|
| Streamlit Cloud URL | https://songdo2-ino.streamlit.app |
| GitHub repo | `sojunghan2000-droid/260423-MPM` |
| 브랜치 | `master` |
| 배포 트리거 | `git push origin master` 시 자동 재빌드 (1~2분) |
| 폰트 파일 위치 | `modules/outputs/fonts/NanumGothic{,Bold}.ttf` |
| baseline commit | `b983c46` (2026-04-27) |

### Cloud 수동 재기동 (코드 변경 없이 캐시만 비우고 싶을 때)
1. https://share.streamlit.io 로그인
2. 해당 앱 → **Manage app → Reboot app**

---

## 7. 회귀 방지 (PR 체크리스트)

PDF 관련 코드를 수정하는 PR은 다음을 확인:

- [ ] `pdf.py`의 폰트 등록 블록에 `_BUNDLE_DIR` + `NanumGothic.ttf` 경로가 포함되어 있는가?
- [ ] `KOREAN_FONT_REGISTERED` / `KOREAN_FONT_DIAG` export가 유지되는가?
- [ ] `try/except: pass` 만으로 폰트 에러를 삼키고 있지 않은가?
- [ ] `modules/outputs/fonts/` 디렉터리와 .ttf 파일이 git-tracked 상태인가? (`git ls-files` 로 확인)
- [ ] 배포 후 새 PDF 1건 생성하여 한글 정상 표시 확인했는가?

---

## 부록 — 영구 해결책 후보 (시간 여유 있을 때)

1. **자동 검증 테스트**: pytest에서 `KOREAN_FONT_REGISTERED == True` 단언 → CI 실패 시 PR 머지 차단
2. **PDF 생성 후 검증**: 첫 페이지에서 한글 ▢ 비율을 측정해 임계치 초과 시 경고
3. **Streamlit Cloud `packages.txt`** 추가: `fonts-nanum` 한 줄 → apt-get 자동 설치 (번들 누락 시에도 backup)
