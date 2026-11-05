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


# 디시 이미지 업로드(gall -> upimg 서브도메인)는 document.domain 공유에 의존하는데 최신 크롬은 이를 기본 차단한다
CHROME_ARGS = ["--disable-features=OriginAgentClusterDefaultEnabled", "--disable-web-security", "--disable-blink-features=AutomationControlled"]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
HIDE_WEBDRIVER = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"


class UploadFailed(RuntimeError):
    pass


class HumanCheckRequired(UploadFailed):
    """디시가 '사람인지 확인' 을 요구함. 자동으로 넘기지 않고 중단한다 (호출한 쪽이 한동안 게시를 쉰다)."""


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

    @staticmethod
    def _is_human_check(msg: str) -> bool:
        import re
        import unicodedata

        t = re.sub(r"\s", "", unicodedata.normalize("NFKC", msg))
        return "사람인지" in t or ("사람" in t and "확인" in t and "체크" in t)

    @staticmethod
    def _body(r):
        try:
            return r.text()[:600]
        except Exception as e:
            return f'(읽기 실패: {str(e)[:80]})'

    @property
    def write_url(self):
        kind = "mgallery/board" if self.minor else "board"
        return f"https://gall.dcinside.com/{kind}/write/?id={self.gallery_id}"

    def _context(self, p, headless):
        return p.chromium.launch_persistent_context(
            self.profile_dir, headless=headless, args=CHROME_ARGS, user_agent=UA, locale="ko-KR", viewport={"width": 1280, "height": 900}
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
        ev = []
        page.on("dialog", lambda d: (ev.append("dialog: " + d.message[:200]), d.dismiss()))
        page.on("console", lambda m: ev.append("console: " + m.text[:200]))
        page.on("pageerror", lambda e: ev.append("pageerror: " + str(e)[:200]))
        page.on("requestfailed", lambda r: ev.append("requestfailed: " + r.url[:100]))
        page.on("response", lambda r: ev.append(f"http {r.status} {r.url[:90]}") if r.status >= 400 or "sign.dcinside" in r.url else None)
        if "sign.dcinside.com" not in page.url:
            from urllib.parse import quote

            page.goto("https://sign.dcinside.com/login?s_url=" + quote(self.write_url, safe=""), wait_until="domcontentloaded")
        try:
            page.wait_for_selector("input[type=password]", state="visible", timeout=20000)
        except Exception:
            # 로그인 입력칸이 안 보임: 어떤 화면이 떴는지 로그에 남긴다 (캡차/차단/점검 구분용, 비밀번호는 포함되지 않음)
            body = " ".join(page.inner_text("body").split())[:300] if page.locator("body").count() else ""
            print("로그인 화면 이벤트:", ev[-20:], "html길이:", len(page.content()))
            raise RuntimeError(f"로그인 입력칸을 찾지 못했습니다. url={page.url} title={page.title()!r} body={body!r}")
        user = page.locator("form input:not([type=hidden]):not([type=password]):not([type=checkbox]):visible").first
        print("로그인 입력칸:", user.get_attribute("name"), user.get_attribute("id"), "| 아이디 길이:", len(self.login_id.strip()), "비밀번호 길이:", len(self.login_pw.strip()))
        user.fill(self.login_id.strip())
        page.locator("input[type=password]:visible").first.fill(self.login_pw.strip())
        page.locator("button[type=submit]:visible, input[type=submit]:visible").first.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)
        if "sign.dcinside.com" in page.url:
            txt = " ".join(page.inner_text("body").split())[:400]
            cap = page.locator("iframe[src*='captcha'], iframe[src*='recaptcha'], iframe[src*='hcaptcha'], [class*='captcha'], [id*='captcha']").count()
            print("로그인 제출 후 화면:", txt, "| 캡차요소 수:", cap, "| 이벤트:", ev[-10:])
            try:
                page.screenshot(path="out/dc_login.png")
            except Exception:
                pass
            raise RuntimeError("로그인에 실패했습니다 (캡차 또는 계정 정보 오류). 캡차는 자동으로 풀지 않습니다.")

    def post(self, title: str, body_text: str, image_path: Path, err_dir: Path) -> None:
        from playwright.sync_api import sync_playwright

        err_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            browser = None
            if self.storage_state:
                browser = p.chromium.launch(headless=not self.headed, args=CHROME_ARGS)
                saved = self.storage_state if Path(self.storage_state).exists() else None
                ctx = browser.new_context(storage_state=saved, user_agent=UA, locale="ko-KR", viewport={"width": 1280, "height": 900})
            else:
                ctx = self._context(p, headless=not self.headed)
            ctx.add_init_script(HIDE_WEBDRIVER)
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
                    nick = page.locator(self.sel["anon_nick"])
                    if nick.is_editable():  # 갤러리가 닉네임을 고정(readonly)해 둔 경우는 그대로 둔다
                        nick.fill(self.anon_nick or "차트봇")
                    page.fill(self.sel["anon_pw"], self.anon_pw)
                if "login" in page.url:
                    raise RuntimeError("로그인 세션이 없습니다. DC_ID/DC_PW 를 넣거나 `python run.py login` 후 세션을 내보내세요.")

                page.fill(self.sel["title"], title)

                if self.headtext and page.locator(self.sel["headtext_open"]).count():
                    page.click(self.sel["headtext_open"])
                    page.click(self.sel["headtext_option"].format(text=self.headtext))

                # 이미지 첨부: 툴바 '이미지' 버튼이 /upload/image 팝업을 연다 -> 팝업의 파일 입력에 넣고 '적용'
                with page.expect_popup(timeout=15000) as pop:
                    page.click(self.sel["image_button"])
                up = pop.value
                msgs = []
                up.on("dialog", lambda d: (msgs.append("dialog: " + d.message), d.dismiss()))
                up.on("console", lambda m: msgs.append("console: " + m.text[:900]))
                up.on("pageerror", lambda e: msgs.append("pageerror: " + str(e)[:200]))
                up.on("response", lambda r: msgs.append(f"http {r.status} {r.url[:120]} body={self._body(r)}") if "upimg_file" in r.url else None)
                up.on("requestfailed", lambda r: msgs.append("requestfailed: " + r.url[:120]))
                up.wait_for_load_state("domcontentloaded")
                up.evaluate("() => { $('#fileupload').fileupload('option', 'xhrFields', {withCredentials: true}); }")  # 교차 도메인 업로드에 로그인 쿠키를 싣는다
                up.evaluate("""() => { const f = $('#fileupload');
                    f.on('fileuploaddone fileuploadfail fileuploadalways', function (e, d) {
                        let r = ''; try { r = JSON.stringify(d.result) + ' | ' + (d.jqXHR && d.jqXHR.responseText || '').slice(0, 500) + ' | ' + (d.textStatus || '') + ' ' + (d.errorThrown || ''); } catch (x) { r = String(x); }
                        console.log('UPLOAD ' + e.type + ': ' + r); }); }""")
                up.wait_for_function("document.getElementById('r_key').value && document.getElementById('gall_no').value", timeout=15000)
                # 팝업 스크립트 자신의 XHR 은 서버에서 빈 응답을 받으므로, 같은 요청을 직접 보내고 응답을 '업로드 성공' 이벤트로 넘겨 준다
                import base64
                up.evaluate("""async (b64) => {
                    const o = $('#fileupload').fileupload('option');
                    const bin = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
                    const fd = new FormData(); fd.append('files[]', new Blob([bin], {type: 'image/png'}), 'chart.png');
                    ['r_key','gall_id','gall_no','post_no','_GALLTYPE_'].forEach(k => fd.append(k, document.getElementById(k).value));
                    fd.append('upload_ing', 'Y');
                    let json = null, r = null, txt = '';
                    for (let i = 0; i < 8 && !json; i++) {
                        await new Promise(res => setTimeout(res, i ? 4000 : 6000));
                        const f2 = new FormData(); for (const [k, v] of fd.entries()) f2.append(k, v);
                        r = await fetch(o.url, {method: 'POST', body: f2, credentials: 'include'});
                        txt = await r.text();
                        console.log('DIRECT try' + i + ' ' + r.status + ' len=' + txt.length);
                        try { json = JSON.parse(txt); } catch (e) { json = null; }
                    }
                    if (!json) throw new Error('업로드 응답 없음: ' + r.status + ' ' + txt.slice(0, 200));
                    console.log('DIRECT ' + r.status + ' ' + JSON.stringify(json).slice(0, 300));
                    document.getElementById('upload_ing').value = 'N';
                    $('.info_box').hide();
                    const inst = $('#fileupload').data('blueimp-fileupload') || $('#fileupload').data('fileupload');
                    inst._trigger('done', $.Event('done'), {result: json, textStatus: 'success', jqXHR: {}, files: [{name: 'chart.png'}]});
                }""", base64.b64encode(Path(image_path).read_bytes()).decode())
                try:
                    up.wait_for_function("document.querySelectorAll('#sortable li .listDelip_img[data-no]').length > 0 && document.getElementById('upload_ing').value !== 'Y'", timeout=25000)
                except Exception:
                    try:
                        up.screenshot(path=str(err_dir / "dc_popup.png"))
                        info = up.evaluate("({ing: document.getElementById('upload_ing') && document.getElementById('upload_ing').value, sortable: (document.getElementById('sortable')||{}).innerHTML, files: (document.querySelector('tbody.files')||{}).innerHTML, text: document.body.innerText.slice(0, 400)})")
                    except Exception as e:
                        info = "popup 상태 읽기 실패: " + str(e)[:150]
                    print("팝업 진단:", str(info)[:700])
                    try:
                        diag = up.evaluate("""async () => {
                            const o = $('#fileupload').fileupload('option');
                            const out = {url: o.url, formData: JSON.stringify(typeof o.formData === 'function' ? o.formData($('#fileupload')) : o.formData), dataType: o.dataType, forceIframe: o.forceIframeTransport, ck: document.cookie.split(';').map(c => c.split('=')[0].trim())};
                            const c = document.createElement('canvas'); c.width = 200; c.height = 120; const g = c.getContext('2d'); g.fillStyle = '#fc0'; g.fillRect(0, 0, 200, 120);
                            const blob = await new Promise(r => c.toBlob(r, 'image/png'));
                            const fd = new FormData(); fd.append('files[]', blob, 'test.png');
                            (JSON.parse(out.formData || '[]') || []).forEach(x => fd.append(x.name, x.value));
                            try { const r = await fetch(o.url, {method: 'POST', body: fd, credentials: 'include'}); out.test = {status: r.status, ct: r.headers.get('content-type'), body: (await r.text()).slice(0, 400)}; } catch (e) { out.test = 'fetch 실패: ' + e; }
                            return out; }""")
                        print("업로드 진단:", str(diag)[:600])
                        import base64
                        b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
                        real = up.evaluate("""async (b64) => {
                            const o = $('#fileupload').fileupload('option'); const res = {};
                            const bin = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
                            const img = await createImageBitmap(new Blob([bin], {type: 'image/png'}));
                            res.dim = img.width + 'x' + img.height;
                            async function send(blob, name) {
                                const fd = new FormData(); fd.append('files[]', blob, name);
                                JSON.parse($('#fileupload').fileupload('option', 'formData') ? '[]' : '[]');
                                ['r_key','gall_id','gall_no','post_no','_GALLTYPE_'].forEach(k => fd.append(k, document.getElementById(k).value));
                                fd.append('upload_ing', 'Y');
                                try { const r = await fetch(o.url, {method: 'POST', body: fd, credentials: 'include'}); const t = await r.text(); return r.status + ' ' + t.length + ' ' + t.slice(0, 160); } catch (e) { return 'fail ' + e; }
                            }
                            res.orig = await send(new Blob([bin], {type: 'image/png'}), 'chart.png');
                            for (const w of [1000, 700]) {
                                const c = document.createElement('canvas'); c.width = w; c.height = Math.round(img.height * w / img.width);
                                c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
                                const b = await new Promise(r => c.toBlob(r, 'image/png'));
                                res['w' + w] = c.width + 'x' + c.height + ' ' + b.size + 'B -> ' + await send(b, 'chart.png');
                            }
                            return res; }""", b64)
                        print("실제 이미지 진단:", str(real)[:1200])
                    except Exception as e:
                        print("업로드 진단 실패:", str(e)[:300])
                    print("팝업 이벤트:", msgs[-25:])
                    raise UploadFailed("이미지 팝업 업로드가 끝나지 않음")
                up.wait_for_timeout(1500)
                up.click("button.btn_apply")
                try:
                    up.wait_for_event("close", timeout=20000)
                except Exception:
                    pass
                page.wait_for_selector(self.sel["editor_img"], timeout=20000)

                # 본문 텍스트: 이미지 뒤에 이어 붙인다
                page.click(self.sel["editor"])
                page.keyboard.press("Control+End")
                page.keyboard.type("\n" + body_text, delay=0)

                dlg = []
                page.on("dialog", lambda d: (dlg.append(d.message[:300]), d.accept()))
                net = []
                page.on("response", lambda r: net.append(f"{r.status} {r.url[:110]}") if ("write" in r.url or "forms" in r.url or "ajax" in r.url) and r.request.method == "POST" else None)
                page.click(self.sel["submit"])
                try:
                    page.wait_for_url(lambda u: "/write" not in u, timeout=20000)
                except Exception:
                    pass
                page.wait_for_timeout(1000)
                if "/write" in page.url and any(self._is_human_check(m) for m in dlg):
                    raise HumanCheckRequired("디시가 '사람인지 확인'을 요구했습니다. 자동 게시를 중단합니다 (수동 게시 또는 갤러리 운영진 협의 필요).")
                if "/write" in page.url:
                    cap =page.locator("iframe[src*='captcha'], iframe[src*='recaptcha'], [class*='captcha']:visible, [id*='captcha']:visible").count()
                    print("등록 후 알림창:", dlg, "| POST응답:", net[-6:], "| 캡차요소:", cap, "| 제목칸:", page.input_value(self.sel["title"])[:40])
                    raise RuntimeError("등록 후에도 글쓰기 화면에 머물러 있습니다 (캡차/도배 제한/필수 항목 누락 가능). url=" + page.url)
            except Exception:
                page.screenshot(path=str(err_dir / "dc_error.png"), full_page=True)
                print("디시 업로드 실패 위치 url:", page.url)
                raise
            finally:
                ctx.close()
                if browser:
                    browser.close()
