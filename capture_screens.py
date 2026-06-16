"""각 화면 스크린샷 캡처"""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("ppt_screens")
OUT.mkdir(exist_ok=True)

def capture(page, name, wait=1.5):
    time.sleep(wait)
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=False)
    print(f"  saved: {name}.png")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1200, "height": 750})
    page = ctx.new_page()

    # 1) 프로젝트 선택
    page.goto("http://localhost:8501")
    capture(page, "01_project_select", wait=3)

    # 프로젝트 선택 → 로그인
    page.locator("[data-testid='stSelectbox']").click()
    time.sleep(0.5)
    page.locator("[data-testid='stSelectboxVirtualDropdown'] li").first.click()
    time.sleep(0.3)
    page.locator("button[kind='primary']").first.click()
    capture(page, "02_login", wait=2)

    # 회원가입
    page.get_by_text("회원가입").click()
    capture(page, "03_signup", wait=1.5)

    # 로그인
    page.get_by_text("← 로그인으로 돌아가기").click()
    time.sleep(0.5)
    page.locator("input[type='text']").fill("pptuser")
    page.locator("input[type='password']").fill("1234")
    page.locator("button[kind='primaryFormSubmit']").click()
    capture(page, "04_home", wait=3)

    # 계획
    page.evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('계획'))?.click()")
    time.sleep(2)
    page.evaluate("window.scrollTo(0, 300)")
    capture(page, "05_schedule", wait=1.5)

    # 승인
    page.evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('승인'))?.click()")
    capture(page, "06_approval", wait=2)

    # 확인
    page.evaluate("(() => { const b = Array.from(document.querySelectorAll('button')).find(x=>x.textContent.trim().includes('확인') && !x.textContent.includes('승인')); b?.click(); })()")
    capture(page, "07_execution", wait=2)

    # 산출물
    page.evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('산출물'))?.click()")
    capture(page, "08_outputs", wait=2)

    # 대장
    page.evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('대장'))?.click()")
    time.sleep(1.5)
    page.evaluate("window.scrollTo(0, 300)")
    capture(page, "09_ledger", wait=1.5)

    # 관리자 설정
    page.evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='⚙️ 관리자')?.click()")
    capture(page, "10_admin", wait=2)

    browser.close()
    print("모든 캡처 완료!")
