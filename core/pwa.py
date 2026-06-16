"""PWA (Progressive Web App) manifest + Apple meta 주입.

Streamlit 기본 `/manifest.json` 은 `name: "Streamlit"` 으로 고정되어 있어
설치 시 PWA 라벨이 "Streamlit" 으로 표시됨. 본 모듈은 parent window 의
<head> 에 데이터 URI 기반 커스텀 manifest 와 Apple iOS 메타태그를 주입해
앱 명칭과 아이콘을 송도2-INO 로 덮어쓴다.

Streamlit 의 `[server] enableStaticServing = true` 옵션이 활성화되어
있어야 하며, 아이콘 파일은 project_root/static/icon-{192,512,180}.png
에 존재해야 함.

사용:
    from core.pwa import inject_pwa
    inject_pwa()   # app.py main() 의 첫 부분에서 호출
"""
from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components


APP_NAME       = "송도2-INO"
APP_SHORT_NAME = "송도2"
APP_DESCRIPTION = "송도역세권 2BL 자재 반출입 관리"
THEME_COLOR     = "#1d4ed8"
BG_COLOR        = "#f8fafc"

# Streamlit 의 정적 서빙 경로. Cloud / localhost 모두 동일 URL 규칙.
# 절대 경로(/app/static/...)로 — manifest 가 data URI 가 아닌 정적 파일이라야
# 상대 경로 해석/아이콘 fetch 가 안정적임 (Chrome PWA 검증 기준).
_MANIFEST_URL = "/app/static/manifest.json?v=3"
_ICON_180     = "/app/static/icon-180.png"


def inject_pwa() -> None:
    """parent window <head> 에 커스텀 manifest + Apple 메타 + 타이틀 주입.

    세션당 1회만 실행. iframe 안에서 parent.document 를 수정한다.
    """
    if st.session_state.get("__pwa_injected"):
        return
    st.session_state["__pwa_injected"] = True

    manifest_uri = _MANIFEST_URL

    components.html(
        f"""
        <script>
        (function() {{
          try {{
            const pdoc = window.parent.document;
            // 이미 한 번 적용했으면 재실행 금지 (멀티 rerun / 중복 inject 방어)
            if (pdoc.__pwaApplied) return;
            pdoc.__pwaApplied = true;

            const OUR_MANIFEST = {json.dumps(manifest_uri)};
            const OUR_TOUCH_ICON = {json.dumps(_ICON_180)};
            const OUR_TITLE = {json.dumps(APP_NAME)};
            const OUR_SHORT = {json.dumps(APP_SHORT_NAME)};
            const OUR_THEME = {json.dumps(THEME_COLOR)};

            // check-before-mutate: 이미 올바른 상태면 DOM 을 건드리지 않는다.
            // (MutationObserver 없이 호출되며, 각 호출은 멱등 + bounded — 무한 루프 불가)
            function applyOverrides() {{
              // 1) manifest <link> — 우리 것이 이미 있으면 아무것도 안 함
              const mls = pdoc.querySelectorAll('link[rel="manifest"]');
              let ourMl = null, hasForeign = false;
              mls.forEach(el => {{
                if (el.href.indexOf(OUR_MANIFEST) !== -1) ourMl = el;
                else hasForeign = true;
              }});
              if (hasForeign) mls.forEach(el => {{ if (el !== ourMl) el.remove(); }});
              if (!ourMl) {{
                ourMl = pdoc.createElement('link');
                ourMl.rel = 'manifest';
                ourMl.href = OUR_MANIFEST;
                pdoc.head.appendChild(ourMl);
              }}

              // 2) Apple iOS 메타 — 값이 다를 때만 setAttribute
              const setMeta = (name, content) => {{
                let el = pdoc.head.querySelector('meta[name="' + name + '"]');
                if (!el) {{
                  el = pdoc.createElement('meta');
                  el.setAttribute('name', name);
                  pdoc.head.appendChild(el);
                }}
                if (el.getAttribute('content') !== content) el.setAttribute('content', content);
              }};
              setMeta('apple-mobile-web-app-title', OUR_SHORT);
              setMeta('apple-mobile-web-app-capable', 'yes');
              setMeta('apple-mobile-web-app-status-bar-style', 'default');
              setMeta('theme-color', OUR_THEME);

              // 3) apple-touch-icon — 우리 것이 이미 있으면 안 함
              const ais = pdoc.querySelectorAll('link[rel="apple-touch-icon"]');
              let ourAi = null, foreignAi = false;
              ais.forEach(el => {{
                if (el.getAttribute('href') === OUR_TOUCH_ICON) ourAi = el;
                else foreignAi = true;
              }});
              if (foreignAi) ais.forEach(el => {{ if (el !== ourAi) el.remove(); }});
              if (!ourAi) {{
                ourAi = pdoc.createElement('link');
                ourAi.rel = 'apple-touch-icon';
                ourAi.href = OUR_TOUCH_ICON;
                pdoc.head.appendChild(ourAi);
              }}

              // 4) 타이틀 — "Streamlit" 일 때만 1회 보정
              if (pdoc.title === 'Streamlit' || !pdoc.title) {{
                pdoc.title = OUR_TITLE;
              }}
            }}

            // 1회 적용 + Streamlit 의 지연 head 삽입 대비 bounded 재시도 2회.
            // setInterval/MutationObserver 미사용 → 메인 스레드 프리즈 불가.
            applyOverrides();
            setTimeout(applyOverrides, 1200);
            setTimeout(applyOverrides, 3000);

            console.log('[pwa] manifest+apple meta injected:', OUR_TITLE);
          }} catch (e) {{
            console.warn('[pwa] inject failed:', e);
          }}
        }})();
        </script>
        """,
        height=0,
    )
