"""디시인사이드 갤러리 글쓰기 (브라우저 자동화).

공식 API가 없어서, 사람이 쓰는 글쓰기 화면을 Playwright 로 그대로 조작한다.
- 로그인은 사용자가 직접 한다 (`python run.py login`). 아이디/비밀번호/캡차를 코드가 다루지 않고,
  로그인 상태는 profile_dir 에 저장된 브라우저 프로필로 유지된다.
- 글쓰기 화면의 선택자는 디시 쪽 개편으로 바뀔 수 있어 config.toml [dc.selectors] 에서 바꿀 수 있다.

!! 이 파일은 실제 로그인 상태에서 검증되지 않았다 (개발 환경에서 디시 계정에 접근할 수 없음).
   처음에는 반드시 `python run.py once --headed` 로 눈으로 보면서 돌려 선택자를 맞출 것.
"""
from __future__ import annotations

from pathlib import Path

DEFAULT_SELECTORS = {
    # 실제 글쓰기 화면(2026-11, fullgirlidol)에서 확인한 값
    "title": "#subject",
    "anon_nick": "#gall_nick_name",
    "anon_pw": "#password",          # 이 칸이 보이면 로그인이 안 된 상태(유동 글쓰기)
    # 말머리: 갤러리에 말머리가 없으면 이 요소가 없어서 건너뜀
    "headtext_open": ".write_subject .subject_list, .write_subject select, #headtext_dropdown",
    "headtext_option": "text={text}",
    # 본문 편집기 (Summernote: iframe 아님)
    "editor": ".note-editable",
    "editor_img": ".note-editable img",
    # 이미지 첨부: 숨겨진 파일 입력에 직접 넣는다. 안 되면 툴바의 '이미지' 버튼 -> 파일 선택창
    "image_input": "#autozzal_image_file",
    "image_button": "button.note-btn:text-is('이미지')",
    "submit": "button.btn_blue.btn_svc.write",
}


class DcUploader:
    def __init__(self, gallery_id: str, headtext: str, profile_dir: str, selectors: dict | None = None,
                 minor: bool = True, headed: bool = False, storage_state: str | None = None,
                 login_id: str | None = None, login_pw: str | None = None,
                 anon_nick: str | None = None, anon_pw: str | None = None):
        self.gallery_id = gallery_id
        self.headtext = headtext
        self.profile_dir = str(Path(profile_dir).expanduser())
        self.sel = {**DEFAULT_SELECTORS, **(selectors or {})}
        self.minor = minor
        self.headed = headed
        self.login_id, self.login_pw = login_id, login_pw  # 있으면 세션이 없을 때 이 계정으로 직접 로그인 (비밀번호는 로그/화면에 남기지 않음)
        self.anon_nick, self.anon_pw = anon_nick, anon_pw  # 로그인이 안 될 때 쓰는 유동(비로그인) 글쓰기용 닉네임/글 비밀번호
        self.storage_state = storage_state  # 있으면 프로필 대신 이 쿠키 파일로 로그인 상태를 복원 (GitHub Actions 등)

    @property
    def write_url(self):
        kind = "mgallery/board" if self.minor else "board"
        return f"https://gall.dcinside.com/{kind}/write/?id={self.gallery_id}"

    def _context(self, p, headless):
        return p.chromium.launch_persistent_context(
            self.profile_dir, headless=headless, locale="ko-KR", viewport={"width": 1280, "height": 900}
        )

    def export_session(self, path: str) -> None:
        """`login` 으로 만든 프로필의 로그인 상태(쿠키)를 파일로 내보낸다. GitHub Secrets 에 넣을 값이다."""
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            ctx = self._context(p, headless=True)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://gall.dcinside.com/", wait_until="domcontentloaded")
            ctx.storage_state(path=path)
            ctx.close()
        Path(path).chmod(0o600)

    def login(self):
        """창을 띄워 사용자가 직접 로그인하게 한다. 로그인 후 창을 닫으면 세션이 프로필에 남는다."""
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            ctx = self._context(p, headless=False)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://sign.dcinside.com/login")
            print("열린 창에서 디시인사이드에 직접 로그인한 뒤, 창을 닫아 주세요.")
            try:
                page.wait_for_event("close", timeout=0)
            except Exception:
                pass
            ctx.close()

    def _sign_in(self, page) -> None:
        """로그인 화면(sign.dcinside.com)에 아이디/비밀번호를 입력한다. 캡차가 뜨면 우회하지 않고 실패 처리한다."""
        if "sign.dcinside.com" not in page.url:
            from urllib.parse import quote

            page.goto("https://sign.dcinside.com/login?s_url=" + quote(self.write_url, safe=""), wait_until="domcontentloaded")
        try:
            page.wait_for_selector("input[type=password]", state="visible", timeout=20000)
        except Exception:
            # 로그인 입력칸이 안 보임: 어떤 화면이 떴는지 로그에 남긴다 (캡차/차단/점검 구분용, 비밀번호는 포함되지 않음)
            body = " ".join(page.inner_text("body").split())[:300] if page.locator("body").count() else ""
            raise RuntimeError(f"로그인 입력칸을 찾지 못했습니다. url={page.url} title={page.title()!r} body={body!r}")
        user = page.locator("form input:not([type=hidden]):not([type=password]):not([type=checkbox]):visible").first
        user.fill(self.login_id)
        page.locator("input[type=password]:visible").first.fill(self.login_pw)
        page.locator("button[type=submit]:visible, input[type=submit]:visible").first.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)
        if "sign.dcinside.com" in page.url:
            raise RuntimeError("로그인에 실패했습니다 (캡차 또는 계정 정보 오류). 캡차는 자동으로 풀지 않습니다.")

    def post(self, title: str, body_text: str, image_path: Path, err_dir: Path) -> None:
        from playwright.sync_api import sync_playwright

        err_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            browser = None
            if self.storage_state:
                browser = p.chromium.launch(headless=not self.headed)
                saved = self.storage_state if Path(self.storage_state).exists() else None
                ctx = browser.new_context(storage_state=saved, locale="ko-KR", viewport={"width": 1280, "height": 900})
            else:
                ctx = self._context(p, headless=not self.headed)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.goto(self.write_url, wait_until="domcontentloaded")
                anon = page.locator(self.sel["anon_nick"]).is_visible()
                if ("login" in page.url or anon) and self.login_id and self.login_pw:
                    try:
                        self._sign_in(page)
                        if self.storage_state:  # 다음 실행에서 다시 로그인하지 않도록 세션 저장
                            ctx.storage_state(path=self.storage_state)
                            Path(self.storage_state).chmod(0o600)
                    except Exception as e:
                        if not self.anon_pw:
                            raise
                        print("로그인 실패, 유동 글쓰기로 진행:", str(e)[:200])
                    page.goto(self.write_url, wait_until="domcontentloaded")
                    anon = page.locator(self.sel["anon_nick"]).is_visible()
                    if anon and not self.anon_pw:
                        raise RuntimeError("로그인 후에도 비로그인(유동) 글쓰기 화면입니다. 계정 정보 또는 캡차를 확인하세요.")
                if anon:
                    if not self.anon_pw:
                        raise RuntimeError("로그인이 안 된 글쓰기 화면입니다. DC_ID/DC_PW 또는 DC_ANON_PW 를 설정하세요.")
                    page.fill(self.sel["anon_nick"], self.anon_nick or "차트봇")
                    page.fill(self.sel["anon_pw"], self.anon_pw)
                if "login" in page.url:
                    raise RuntimeError("로그인 세션이 없습니다. DC_ID/DC_PW 를 넣거나 `python run.py login` 후 세션을 내보내세요.")

                page.fill(self.sel["title"], title)

                if self.headtext and page.locator(self.sel["headtext_open"]).count():
                    page.click(self.sel["headtext_open"])
                    page.click(self.sel["headtext_option"].format(text=self.headtext))

                # 이미지 첨부: 숨겨진 파일 입력에 바로 넣고, 편집기에 이미지가 들어갔는지 확인
                page.set_input_files(self.sel["image_input"], str(image_path))
                try:
                    page.wait_for_selector(self.sel["editor_img"], timeout=20000)
                except Exception:
                    # 입력칸이 반응하지 않으면 툴바의 '이미지' 버튼으로 파일 선택창을 연다
                    with page.expect_file_chooser(timeout=8000) as fc:
                        page.click(self.sel["image_button"])
                    fc.value.set_files(str(image_path))
                    page.wait_for_selector(self.sel["editor_img"], timeout=20000)

                # 본문 텍스트: 이미지 뒤에 이어 붙인다
                page.click(self.sel["editor"])
                page.keyboard.press("Control+End")
                page.keyboard.type("\n" + body_text, delay=0)

                page.click(self.sel["submit"])
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(2000)
                if "/write" in page.url:
                    raise RuntimeError("등록 후에도 글쓰기 화면에 머물러 있습니다 (캡차/도배 제한/필수 항목 누락 가능). url=" + page.url)
            except Exception:
                page.screenshot(path=str(err_dir / "dc_error.png"), full_page=True)
                print("디시 업로드 실패 위치 url:", page.url)
                raise
            finally:
                ctx.close()
                if browser:
                    browser.close()
