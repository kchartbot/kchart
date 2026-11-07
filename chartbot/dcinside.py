from __future__ import annotations

from pathlib import Path
import os
import time
import random
import base64

DEFAULT_SELECTORS = {
    "title": "#subject",
    "anon_nick": "#gall_nick_name",
    "anon_pw": "#password",
    "headtext_open": ".write_subject .subject_list, .write_subject select, #headtext_dropdown",
    "headtext_option": "text={text}",
    "editor": ".note-editable",
    "editor_img": ".note-editable img",
    "image_input": "#autozzal_image_file",
    "image_button": "button.note-btn:text-is('이미지')",
    "submit": "button.btn_blue.btn_svc.write",
}

CHROME_ARGS = [
    "--disable-features=OriginAgentClusterDefaultEnabled",
    "--disable-web-security",
    "--disable-blink-features=AutomationControlled"
]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"

HIDE_WEBDRIVER = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
Object.defineProperty(navigator, 'languages', {get: () => ['ko-KR', 'ko', 'en-US', 'en']});
window.chrome = { runtime: {} };
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
    Promise.resolve({ state: Notification.permission }) :
    originalQuery(parameters)
);
"""

class UploadFailed(RuntimeError):
    pass

class HumanCheckRequired(UploadFailed):
    pass

class DcUploader:
    def __init__(self, gallery_id: str, headtext: str, profile_dir: str, selectors: dict | None = None,
                 minor: bool = True, headed: bool = False, storage_state: str | None = None,
                 login_id: str | None = None, login_pw: str | None = None,
                 anon_nick: str | None = None, anon_pw: str | None = None, kind: str | None = None,
                 proxy: str | None = None):
        self.gallery_id = gallery_id
        self._kind = {"mini": "mini/board", "minor": "mgallery/board", "mgallery": "mgallery/board", "main": "board", "board": "board"}.get((kind or "").strip().lower())
        self.headtext = headtext
        self.profile_dir = str(Path(profile_dir).expanduser())
        self.sel = {**DEFAULT_SELECTORS, **(selectors or {})}
        self.minor = minor
        self.headed = headed
        self.login_id, self.login_pw = login_id, login_pw
        self.anon_nick, self.anon_pw = anon_nick, (anon_pw if os.environ.get("DC_ALLOW_ANON", "").lower() == "true" else None)
        self.storage_state = storage_state
        self.proxy = proxy

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
        kind = self._kind or ("mgallery/board" if self.minor else "board")
        return f"https://gall.dcinside.com/{kind}/write/?id={self.gallery_id}"

    def _is_anon(self, page) -> bool:
        try:
            fields = page.evaluate("() => [...document.querySelectorAll('input')].filter(e => e.offsetParent).map(e => (e.id || '') + '/' + (e.name || '') + '/' + e.type)")
        except Exception:
            fields = []
        anon = any(f.startswith(("password/", "name/", "gall_nick_name/")) for f in fields)
        print("글쓰기 화면 입력칸:", fields[:12], "-> 비로그인" if anon else "-> 로그인됨")
        return anon

    def _pick_headtext(self, page) -> None:
        want = self.headtext
        forced = os.environ.get("DC_HEAD_NO", "").strip()
        res = page.evaluate("""([want, forced]) => {
            const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
            const root = document.querySelector('.write_subject, .subject_list, #write') || document.body;
            const attrs = ['data-no', 'data-headno', 'data-head-no', 'data-value', 'data-idx', 'data-val', 'value'];
            const cands = [...root.querySelectorAll('li, a, button, label, span, div, option')]
                .filter(e => { const t = (e.innerText || e.textContent || '').trim(); return (t === want || t.includes(want) || (e.getAttribute('data-val') || '').includes(want)) && !e.querySelector('input,textarea') && e.children.length < 3; });
            cands.sort((a, b) => ((a.innerText || a.textContent || '').trim().length - (b.innerText || b.textContent || '').trim().length) || a.querySelectorAll('*').length - b.querySelectorAll('*').length);
            const out = {n: cands.length, html: cands[0] ? cands[0].outerHTML.slice(0, 300) : null, no: forced || null, clicked: false};
            if (!out.no) {
                for (const e of cands) {
                    for (let x = e, d = 0; x && d < 3 && !out.no; x = x.parentElement, d++) {
                        for (const a of attrs) { const v = x.getAttribute(a); if (v && /^[0-9]+$/.test(v)) { out.no = v; break; } }
                    }
                    if (out.no) break;
                }
            }
            if (!out.no && cands[0]) { for (const e of cands) { const v = e.getAttribute('data-no'); if (v && /^[0-9]+$/.test(v)) { out.no = v; break; } } }
            const vc = cands.find(vis);
            if (!vc && cands[0]) { cands[0].click(); out.clicked = true; }
            if (vc) { vc.scrollIntoView({block: 'center'}); const r = vc.getBoundingClientRect(); out.x = r.x + r.width / 2; out.y = r.y + r.height / 2; }
            out.inputs = [...document.querySelectorAll('input[name*=head], input[id*=head]')].map(i => i.name + '#' + i.id + '=' + i.value);
            return out;
        }""", [want, forced])
        if res.get("x") is not None:
            page.mouse.click(res["x"], res["y"])
            res["clicked"] = True
        elif page.locator(self.sel["headtext_open"]).count():
            page.click(self.sel["headtext_open"])
            page.click(self.sel["headtext_option"].format(text=want))
            res["clicked"] = True
        if res.get("no"):
            page.evaluate("""(no) => {
                let i = document.querySelector('input[name=head_no]');
                if (!i) { i = document.createElement('input'); i.type = 'hidden'; i.name = 'head_no'; (document.querySelector('form#write, form[name=write], form') || document.body).appendChild(i); }
                i.value = no;
            }""", res["no"])
        after = page.evaluate("() => [...document.querySelectorAll('input[name=head_no], input[name*=headtext]')].map(i => i.name + '=' + i.value)")
        print("말머리:", want, "| 후보", res.get("n"), "| 번호", res.get("no"), "| 클릭", res.get("clicked"), "| 입력칸", res.get("inputs"), "->", after, "|", (res.get("html") or "")[:200])

    def _solve_turnstile(self, page) -> None:
        try:
            for _ in range(3):
                frames = page.locator("iframe[src*='challenges.cloudflare.com'], iframe[src*='turnstile'], #dc-turnstile")
                if frames.count() == 0:
                    break
                
                box = frames.first.bounding_box()
                if box and box["width"] > 50:
                    print("페이지 인증 처리 중...")
                    x = box["x"] + box["width"] * 0.11
                    y = box["y"] + box["height"] * 0.5
                    page.mouse.move(x - random.randint(15, 40), y + random.randint(-10, 10), steps=random.randint(5, 10))
                    time.sleep(random.uniform(0.2, 0.5))
                    page.mouse.move(x, y, steps=random.randint(3, 7))
                    time.sleep(random.uniform(0.1, 0.3))
                    page.mouse.down()
                    time.sleep(random.uniform(0.05, 0.15))
                    page.mouse.up()
                
                page.wait_for_timeout(random.randint(2000, 4000))
        except Exception:
            pass

    def _click_submit(self, page) -> None:
        # [핵심 수정] 네이티브 form.submit() 대신 jQuery submit 이벤트 트리거
        try:
            print("등록 폼 jQuery 전송 시도...")
            page.evaluate("""() => {
                const cb = document.getElementById('clickbutton');
                if (cb) cb.value = 'Y';
                
                if (window.jQuery) {
                    const $form = window.jQuery('form[name=write], form#write');
                    if ($form.length > 0) {
                        $form.submit();
                        return;
                    }
                }
                
                // jQuery가 없을 경우 dispatchEvent로 submit 이벤트 발생
                const form = document.querySelector('form[name=write], form#write');
                if (form) {
                    form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
                }
            }""")
            return
        except Exception as e:
            print("JS 전송 실패, 버튼 클릭으로 폴백:", str(e)[:100])

        cands = [self.sel["submit"], "button.btn_svc.write", ".btn_blue.small.write", "button.write", "a.write",
                 "input[type=submit][value*='등록']", "button:text-is('등록')", "a:text-is('등록')", "button:has-text('등록')", "a:has-text('등록')"]
        for c in cands:
            loc = page.locator(c)
            try:
                if loc.count() and loc.first.is_visible():
                    print("등록 버튼:", c)
                    time.sleep(random.uniform(0.5, 1.2))
                    loc.first.click()
                    return
            except Exception:
                continue
        info = page.evaluate("() => [...document.querySelectorAll('button, a.btn, input[type=submit], input[type=button]')].filter(e => e.offsetParent).map(e => (e.tagName + '.' + (e.className || '') + ' ' + (e.innerText || e.value || '')).trim().slice(0, 70)).slice(0, 40)")
        print("등록 버튼을 못 찾음. 보이는 버튼들:", info)
        raise RuntimeError("등록 버튼을 찾지 못했습니다")

    def _open_write(self, page, alerts) -> None:
        first = self._kind or ("mgallery/board" if self.minor else "board")
        order = [first] + [k for k in ("mgallery/board", "board", "mini/board") if k != first]
        tried = []
        for kind in order:
            self._kind = kind
            page.goto(self.write_url, wait_until="domcontentloaded")
            
            try:
                for _ in range(5):
                    has_frame = page.locator("#dc-turnstile").count() > 0 or page.locator("iframe[src*='challenges.cloudflare.com']").count() > 0
                    if has_frame:
                        self._solve_turnstile(page)
                    else:
                        break
            except Exception:
                pass

            ok = False
            try:
                page.wait_for_selector(self.sel["title"], timeout=10000)
                ok = True
            except Exception:
                ok = "login" in page.url
            tried.append(f"{kind} -> {page.url[:90]} ({'열림' if ok else '안 열림'})")
            if ok:
                if kind != first:
                    print("갤러리 종류가 설정과 달라 자동으로 바꿨습니다:", kind)
                return
        print("글쓰기 화면을 열지 못함. 시도:", tried, "| 알림창:", alerts)
        raise RuntimeError("글쓰기 화면이 열리지 않습니다 (갤러리 ID 오류 또는 글쓰기 권한 없음). 알림창: " + str(alerts))

    def _context(self, p, headless):
        launch_kwargs = {
            "headless": headless,
            "args": CHROME_ARGS,
            "user_agent": UA,
            "locale": "ko-KR",
            "viewport": {"width": 1280, "height": 900}
        }
        if self.proxy:
            launch_kwargs["proxy"] = {"server": self.proxy}
            
        return p.chromium.launch_persistent_context(self.profile_dir, **launch_kwargs)

    def export_session(self, path: str) -> None:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            ctx = self._context(p, headless=True)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://gall.dcinside.com/", wait_until="domcontentloaded")
            ctx.storage_state(path=path)
            ctx.close()
        Path(path).chmod(0o600)

    def login(self):
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
            body = " ".join(page.inner_text("body").split())[:300] if page.locator("body").count() else ""
            print("로그인 화면 이벤트:", ev[-20:], "html길이:", len(page.content()))
            raise RuntimeError(f"로그인 입력칸을 찾지 못했습니다. url={page.url} title={page.title()!r} body={body!r}")
        
        user = page.locator("form input:not([type=hidden]):not([type=password]):not([type=checkbox]):visible").first
        print("로그인 입력칸:", user.get_attribute("name"), user.get_attribute("id"), "| 아이디 길이:", len(self.login_id.strip()), "비밀번호 길이:", len(self.login_pw.strip()))
        
        user.fill(self.login_id.strip())
        time.sleep(random.uniform(0.3, 0.8))
        page.locator("input[type=password]:visible").first.fill(self.login_pw.strip())
        time.sleep(random.uniform(0.5, 1.0))
        
        page.locator("button[type=submit]:visible, input[type=submit]:visible").first.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)
        
        if "sign.dcinside.com" in page.url:
            txt = " ".join(page.inner_text("body").split())[:400]
            cap = page.locator("iframe[src*='captcha'], iframe[src*='recaptcha'], iframe[src*='hcaptcha'], [class*='captcha'], [id*='captcha']").count()
            print("로그인 제출 후 화면:", txt, "| 요소 수:", cap, "| 이벤트:", ev[-10:])
            try:
                page.screenshot(path="out/dc_login.png")
            except Exception:
                pass
            raise RuntimeError("로그인에 실패했습니다.")

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
            alerts = []
            
            def handle_dialog(d):
                try:
                    msg = d.message[:300]
                    alerts.append(msg)
                    d.accept()
                except Exception:
                    pass
            
            page.on("dialog", handle_dialog)

            try:
                self._open_write(page, alerts)
                anon = self._is_anon(page)
                
                if ("login" in page.url or anon) and self.login_id and self.login_pw:
                    try:
                        self._sign_in(page)
                        if self.storage_state:
                            ctx.storage_state(path=self.storage_state)
                            Path(self.storage_state).chmod(0o600)
                    except Exception as e:
                        if not self.anon_pw:
                            raise
                        print("로그인 실패, 유동 글쓰기로 진행:", str(e)[:200])
                    
                    self._open_write(page, alerts)
                    anon = self._is_anon(page)
                    if anon and not self.anon_pw:
                        raise RuntimeError("로그인 후에도 비로그인(유동) 글쓰기 화면입니다. 계정 정보를 확인하세요.")
                
                if anon:
                    if not self.anon_pw:
                        raise RuntimeError("로그인이 안 된 글쓰기 화면입니다. DC_ID/DC_PW 또는 DC_ANON_PW 를 설정하세요.")
                    nick = page.locator(self.sel["anon_nick"])
                    if nick.is_editable():
                        nick.fill(self.anon_nick or "차트봇")
                    page.fill(self.sel["anon_pw"], self.anon_pw)
                
                if "login" in page.url:
                    raise RuntimeError("로그인 세션이 없습니다. DC_ID/DC_PW 를 넣거나 `python run.py login` 후 세션을 내보내세요.")

                page.fill(self.sel["title"], title)
                time.sleep(random.uniform(0.5, 1.5))

                if self.headtext:
                    self._pick_headtext(page)
                    time.sleep(random.uniform(0.5, 1.0))

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
                up.evaluate("() => { $('#fileupload').fileupload('option', 'xhrFields', {withCredentials: true}); }")
                up.evaluate("""() => { const f = $('#fileupload');
                    f.on('fileuploaddone fileuploadfail fileuploadalways', function (e, d) {
                        let r = ''; try { r = JSON.stringify(d.result) + ' | ' + (d.jqXHR && d.jqXHR.responseText || '').slice(0, 500) + ' | ' + (d.textStatus || '') + ' ' + (d.errorThrown || ''); } catch (x) { r = String(x); }
                        console.log('UPLOAD ' + e.type + ': ' + r); }); }""")
                up.wait_for_function("document.getElementById('r_key').value && document.getElementById('gall_no').value", timeout=15000)
                
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
                        b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
                        real = up.evaluate("""async (b64) => {
                            const o = $('#fileupload').fileupload('option'); const res = {};
                            const bin = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
                            const img = await createImageBitmap(new Blob([bin], {type: 'image/png'}));
                            res.dim = img.width + 'x' + img.height;
                            async function send(blob, name) {
                                const fd = new FormData(); fd.append('files[]', blob, name);
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
                
                up.evaluate("""() => {
                    $('#sortable li').addClass('sel');
                    const btn = document.querySelector('button.btn_apply') || document.querySelector('.btn_apply');
                    if (btn) btn.click();
                }""")

                try:
                    up.wait_for_event("close", timeout=20000)
                except Exception:
                    try:
                        up.close()
                    except Exception:
                        pass
                
                page.wait_for_selector(self.sel["editor_img"], timeout=70000)

                page.click(self.sel["editor"])
                page.keyboard.press("Control+End")
                time.sleep(random.uniform(0.5, 1.0))
                
                for char in "\n" + body_text:
                    page.keyboard.type(char, delay=random.randint(30, 80))
                    if random.random() < 0.05:
                        time.sleep(random.uniform(0.1, 0.3))

                dlg = alerts
                net = []
                page.on("response", lambda r: net.append(f"{r.status} {r.url[:110]}") if ("write" in r.url or "forms" in r.url or "ajax" in r.url) and r.request.method == "POST" else None)
                
                self._solve_turnstile(page)

                self._click_submit(page)
                page.wait_for_timeout(2000)
                
                if any("보안 확인" in m for m in dlg):
                    print("추가 보안 확인 진행 중...")
                    page.wait_for_timeout(random.randint(2000, 4000))
                    
                    page.evaluate("""() => {
                        const cb = document.getElementById('clickbutton');
                        if (cb) cb.value = 'N';
                        const btn = document.querySelector('button.btn_blue.btn_svc.write');
                        if (btn) btn.disabled = false;
                    }""")
                    
                    dlg.clear()
                    self._solve_turnstile(page)
                    self._click_submit(page)

                try:
                    page.wait_for_url(lambda u: "/write" not in u, timeout=25000)
                except Exception:
                    pass
                page.wait_for_timeout(1000)
                
                if "/write" in page.url and any(self._is_human_check(m) for m in dlg):
                    print(">>> 디시인사이드 알림창 내용:", dlg)
                    raise HumanCheckRequired("게시글 등록이 차단되었습니다. 잠시 후 다시 시도해 주세요.")
                
                if "/write" in page.url:
                    cap = page.locator("iframe[src*='captcha'], iframe[src*='recaptcha'], [class*='captcha']:visible, [id*='captcha']:visible").count()
                    print("등록 후 알림창:", dlg, "| POST응답:", net[-6:], "| 확인 필요:", cap, "| 제목칸:", page.input_value(self.sel["title"])[:40])
                    raise RuntimeError("등록 후에도 글쓰기 화면에 머물러 있습니다. url=" + page.url)
            except Exception:
                page.screenshot(path=str(err_dir / "dc_error.png"), full_page=True)
                print("디시 업로드 실패 위치 url:", page.url)
                raise
            finally:
                ctx.close()
                if browser:
                    browser.close()
