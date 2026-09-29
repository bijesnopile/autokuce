"""Screenshotovi i provjera "kao klijent" (Playwright, Chromium) — Windows i Linux.

    python scripts/screenshots.py                # sve u docs/screenshots/
    python scripts/screenshots.py --out mapa     # drugdje

Skripta pokreće VLASTITU instancu (privremena SQLite baza + puni demo seed, emailovi u
privremeni outbox) na slobodnom portu, pa ne dira tvoju lokalnu bazu. Zatim prolazi tijekove
kao posjetitelj i kao administrator (pretraga → upit → newsletter s potvrdom iz emaila → prijava
s postavljanjem 2FA → obrada upita → kampanja s vozilom → slanje) i snima stranice na desktopu
(1440×900) i mobitelu (390×844). Za svaku stranicu provjerava HTTP status, horizontalni skrol i
greške u konzoli preglednika; izlazni kod 1 ako nešto ne valja.

Instanca radi s PLAN=standard (WhatsApp, kalkulator rate, kartica za izlog, ponuda, termini, feed).
Na kraju superadmin na stranici Sustav nadjača paket na Osnovni i snimi zaključane stavke
(oznake u izborniku, stranica "Dostupno u paketu Standard"), pa nadjačavanje ukloni.

Preduvjet: pip install -r requirements-dev.txt && python -m playwright install chromium
"""

from __future__ import annotations

import argparse
import email
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from email import policy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.utils import ensure_utf8_console  # noqa: E402

PASSWORD = "Promijeni-me-2026!"
DESKTOP = {"width": 1440, "height": 900}
MOBILE = {"width": 390, "height": 844}


class Run:
    """Collects screenshots and problems found along the way."""

    def __init__(self, base: str, out: Path, outbox: Path) -> None:
        self.base = base
        self.out = out
        self.outbox = outbox
        self.shots: list[str] = []
        self.problems: list[str] = []
        self.console: list[str] = []
        self.expected_errors: set[str] = set()

    def watch(self, page) -> None:
        def on_console(msg) -> None:
            if msg.type != "error":
                return
            # The browser logs intentionally requested error pages (404, 403) as errors.
            if any(page.url.endswith(path) for path in self.expected_errors):
                if "Failed to load resource" in msg.text:
                    return
            self.console.append(f"{page.url}: {msg.text}")

        page.on("console", on_console)

    def goto(self, page, path: str, expect: int = 200):
        if expect >= 400:
            self.expected_errors.add(path)
        response = page.goto(self.base + path)
        status = response.status if response else 0
        if status != expect:
            self.problems.append(f"{path}: HTTP {status} (očekivano {expect})")
        return response

    def check_layout(self, page, name: str) -> None:
        width = page.viewport_size["width"]
        scroll = page.evaluate("document.documentElement.scrollWidth")
        if scroll > width + 1:
            self.problems.append(f"{name}: horizontalni skrol ({scroll}px > {width}px)")

    def shot(self, page, name: str, full: bool = True) -> None:
        """Full-page screenshot: load lazy images, sticky bars static (capture only)."""
        self.check_layout(page, name)
        if full:
            # The site uses smooth scrolling; the capture needs instant jumps.
            page.add_style_tag(content="html{scroll-behavior:auto!important}")
            # Scroll through the page (lazy images start loading), then wait until every
            # image has loaded (max 5 s) before going back to the top.
            page.evaluate(
                "async () => { for (let y = 0; y < document.body.scrollHeight; y += 500) "
                "{ window.scrollTo(0, y); await new Promise(r => setTimeout(r, 60)); } "
                "await Promise.all([...document.images].filter(i => !i.complete).map(i => "
                "new Promise(r => { i.addEventListener('load', r); i.addEventListener('error', r); "
                "setTimeout(r, 5000); }))); window.scrollTo({top: 0, behavior: 'instant'}); }"
            )
            page.add_style_tag(
                content=".sticky-actions{position:static!important}"
                ".sticky-cta{display:none!important}"
            )
            page.wait_for_timeout(250)
        page.screenshot(path=str(self.out / f"{name}.png"), full_page=full)
        self.shots.append(f"{name}.png")

    def newest_mail(self, to: str):
        for _ in range(20):
            for path in sorted(self.outbox.glob("*.eml"), key=lambda p: p.stat().st_mtime)[::-1]:
                message = email.message_from_bytes(path.read_bytes(), policy=policy.default)
                if message["To"] == to:
                    return message
            time.sleep(0.25)
        raise AssertionError(f"nema emaila za {to}")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_instance(tmp: Path, port: int) -> subprocess.Popen:
    env = dict(os.environ)
    env.update(
        APP_ENV="development",
        DATA_DIR=str(tmp),
        DATABASE_URL="",
        EMAIL_BACKEND="file",
        BASE_URL=f"http://127.0.0.1:{port}",
        SEED_PASSWORD=PASSWORD,
        PLAN="standard",
        MAINTENANCE_IN_APP="false",
        TURNSTILE_SITE_KEY="",
        TURNSTILE_SECRET_KEY="",
        UMAMI_SCRIPT_URL="",
        UMAMI_WEBSITE_ID="",
        PYTHONIOENCODING="utf-8",
    )
    print("[screenshots] migracije i demo seed (privremena baza)...", flush=True)
    for args in (["-m", "app.cli", "migrate"], ["-m", "app.seed"]):
        subprocess.run(
            [sys.executable, *args],
            cwd=ROOT,
            env=env,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    log = open(tmp / "server.log", "w", encoding="utf-8")  # noqa: SIM115 - closed by process
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    for _ in range(120):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/zdravlje", timeout=2):
                return server
        except OSError:
            time.sleep(0.5)
    server.terminate()
    raise RuntimeError("server se nije pokrenuo — vidi " + str(tmp / "server.log"))


def public_flows(run: Run, browser) -> None:
    # --- Desktop ------------------------------------------------------------------------
    ctx = browser.new_context(viewport=DESKTOP)
    page = ctx.new_page()
    run.watch(page)
    run.goto(page, "/")
    run.shot(page, "javno-naslovnica-desktop")
    # Pretraga s naslovnice: marka Škoda → lista → detalj.
    skoda = page.eval_on_selector(
        "#qs-marka", "s => [...s.options].find(o => o.text.startsWith('Škoda')).value"
    )
    page.select_option("#qs-marka", skoda)
    page.click(".quick-search button[type=submit]")
    page.wait_for_load_state()
    assert "Octavia" in page.content(), "pretraga po marki ne vraća Octaviju"
    page.click(".vehicle-card a >> nth=0")
    page.wait_for_load_state()
    detail = page.url.replace(run.base, "")
    run.goto(page, "/vozila")
    run.shot(page, "javno-lista-desktop")
    run.goto(page, detail)
    run.shot(page, "javno-detalj-desktop")
    # Paket Standard: kalkulator rate (klizači mijenjaju ratu i formu upita za financiranje).
    before = page.inner_text("[data-fin-payment]")
    page.fill("[data-fin-down]", "40")
    page.dispatch_event("[data-fin-down]", "input")
    assert page.inner_text("[data-fin-payment]") != before, "kalkulator rate ne reagira"
    page.click("#financiranje-upit summary")
    page.wait_for_timeout(200)
    element_shot(run, page, "#financiranje", "javno-financiranje-desktop")
    page.click("[data-gallery-main]")
    page.wait_for_timeout(500)
    run.shot(page, "javno-lightbox-desktop", full=False)
    page.keyboard.press("Escape")
    run.goto(page, "/kontakt")
    run.shot(page, "javno-kontakt-desktop")
    run.goto(page, "/privatnost")
    run.shot(page, "javno-privatnost-desktop")
    run.goto(page, "/usluge")
    run.shot(page, "javno-usluge-desktop")
    run.goto(page, "/o-nama")
    run.shot(page, "javno-o-nama-desktop")
    ctx.close()

    # --- Mobile: upit s detalja + newsletter s potvrdom iz emaila ------------------------
    ctx = browser.new_context(viewport=MOBILE)
    page = ctx.new_page()
    run.watch(page)
    for path, name in (
        ("/", "naslovnica"),
        ("/vozila", "lista"),
        (detail, "detalj"),
        ("/kontakt", "kontakt"),
        ("/usluge", "usluge"),
        ("/o-nama", "o-nama"),
    ):
        run.goto(page, path)
        run.shot(page, f"javno-{name}-mobile")
    run.goto(page, "/ne-postoji", expect=404)
    run.shot(page, "javno-404-mobile")

    # Paket Standard na mobitelu: WhatsApp/Viber u donjoj traci i kalkulator rate.
    run.goto(page, detail)
    page.wait_for_timeout(300)
    assert page.locator(".sticky-cta .btn-whatsapp").count() == 1, "nema WhatsApp gumba"
    page.screenshot(path=str(run.out / "javno-whatsapp-mobile.png"))
    run.shots.append("javno-whatsapp-mobile.png")
    element_shot(run, page, "#financiranje", "javno-financiranje-mobile")

    run.goto(page, detail)
    page.click(".sticky-cta [data-scroll-to-form]")
    page.wait_for_timeout(500)
    page.fill("#upit-name", "Ime Prezime")
    page.fill("#upit-email", "kupac.test@primjer.hr")
    page.fill("#upit-phone", "091 234 5678")
    page.check("#upit input[name=consent]")
    page.wait_for_timeout(400)  # the bottom bar slides away while the form is in view
    page.locator("#upit").screenshot(path=str(run.out / "javno-upit-forma-mobile.png"))
    run.shots.append("javno-upit-forma-mobile.png")
    page.wait_for_timeout(3200)  # forme poslane brže od 3 s odbijaju se kao botovi
    page.click("#upit button[type=submit]")
    page.wait_for_load_state()
    assert "Hvala, javit ćemo vam se" in page.content(), "upit nije prihvaćen"
    run.newest_mail(os.environ.get("AK_NOTIFY", "mailpoduzeca@domena.com"))

    address = f"citatelj{int(time.time())}@primjer.hr"
    run.goto(page, "/")
    page.fill("#nl-footer-email", address)
    page.check(".footer-newsletter input[name=consent]")
    page.wait_for_timeout(3200)
    page.click(".footer-newsletter button[type=submit]")
    page.wait_for_load_state()
    message = run.newest_mail(address)
    link = re.search(
        r"http://\S+/newsletter/potvrda/\S+", message.get_body(("plain",)).get_content()
    ).group(0)
    page.goto(link)
    assert "Prijava je potvrđena" in page.content(), "potvrda newslettera nije uspjela"
    run.shot(page, "javno-newsletter-potvrda-mobile")
    ctx.close()
    print("[screenshots] javni tijekovi: pretraga, upit, newsletter — OK", flush=True)


def element_shot(run: Run, page, selector: str, name: str) -> None:
    """Screenshot of one element (after scrolling it into view; lazy images loaded)."""
    run.check_layout(page, name)
    page.add_style_tag(content=".sticky-cta{display:none!important}")
    locator = page.locator(selector)
    locator.scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    locator.screenshot(path=str(run.out / f"{name}.png"))
    run.shots.append(f"{name}.png")


def admin_login(run: Run, page) -> None:
    import pyotp

    run.goto(page, "/admin/prijava")
    run.shot(page, "admin-prijava")
    page.fill("#email", "admin@domena.com")
    page.fill("#password", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_url("**/admin/2fa/postavljanje")
    run.shot(page, "admin-2fa-postavljanje")
    secret = page.inner_text("#manual-key").replace(" ", "")
    page.fill("#code", pyotp.TOTP(secret).now())
    page.click("form button[type=submit]")
    page.wait_for_selector("#recovery-codes")
    page.click("text=nastavi")
    page.wait_for_url(run.base + "/admin**")


def set_plan_override(page, run: Run, plan: str) -> None:
    run.goto(page, "/admin/sustav")
    page.select_option("#plan-override", plan)
    page.click("form[action='/admin/sustav/paket'] button[type=submit]")
    page.wait_for_load_state()


def admin_flows(run: Run, browser, state_file: Path) -> None:
    ctx = browser.new_context(viewport=DESKTOP, bypass_csp=True)
    page = ctx.new_page()
    run.watch(page)
    admin_login(run, page)
    ctx.storage_state(path=str(state_file))

    run.goto(page, "/admin")
    run.shot(page, "admin-dashboard-desktop")
    run.goto(page, "/admin/vozila")
    run.shot(page, "admin-vozila")
    vehicle_path = re.search(r'href="(/admin/vozila/\d+)"', page.content()).group(1)
    run.goto(page, vehicle_path)
    run.shot(page, "admin-vozilo-forma")
    run.goto(page, vehicle_path + "/slike")
    run.shot(page, "admin-vozilo-slike")

    # Paket Standard: kartica za izlog (A4 i A5) i ponuda kupcu.
    run.goto(page, vehicle_path + "/izlog")
    run.shot(page, "admin-izlog-kartica-a4")
    run.goto(page, vehicle_path + "/izlog?format=a5")
    run.shot(page, "admin-izlog-kartica-a5")
    run.goto(page, vehicle_path + "/ponuda")
    page.fill("#customer_name", "Ime Prezime")
    page.fill("#customer_email", "kupac@primjer.hr")
    page.fill("#discount", "500")
    page.click("form[action$='/ponuda'] button[type=submit]")
    page.wait_for_load_state()
    assert "Ponuda br." in page.content(), "ponuda nije izrađena"
    run.shot(page, "admin-ponuda")

    # Obrada upita koji je poslan s javne stranice.
    run.goto(page, "/admin/upiti")
    run.shot(page, "admin-upiti")
    page.click(".title-cell a >> nth=0")
    page.wait_for_url("**/admin/upiti/*")
    assert "kupac.test@primjer.hr" in page.content(), "najnoviji upit nije testni upit"
    page.select_option("#status", "contacted")
    page.click("form[action$='/status'] button")
    page.wait_for_load_state()
    page.fill("#note-body", "Nazvao kupca, dogovoren pregled u subotu u 10 h.")
    page.click("form[action$='/biljeske'] button")
    page.wait_for_load_state()
    assert "Nazvao kupca" in page.content(), "bilješka nije spremljena"
    run.shot(page, "admin-upit-detalj")

    # Paket Standard: potvrda termina pregleda (.ics kupcu) i upit za financiranje.
    run.goto(page, "/admin/upiti?tip=viewing&status=new")
    page.click(".title-cell a >> nth=0")
    page.wait_for_url("**/admin/upiti/*")
    page.click("#termin button[type=submit]")
    page.wait_for_load_state()
    assert "Termin je potvrđen" in page.content(), "termin nije potvrđen"
    run.shot(page, "admin-upit-termin")
    run.goto(page, "/admin/upiti?tip=financing")
    page.click(".title-cell a >> nth=0")
    page.wait_for_url("**/admin/upiti/*")
    assert "Zatraženo financiranje" in page.content(), "nema parametara financiranja"
    run.shot(page, "admin-upit-financiranje")

    # Newsletter: kampanja s umetnutim vozilom → testni email → slanje → izvještaj.
    run.goto(page, "/admin/newsletter/pretplatnici")
    run.shot(page, "admin-newsletter-pretplatnici")
    run.goto(page, "/admin/newsletter/kampanje/nova")
    page.fill("#subject", "Nova vozila u ponudi")
    page.click(".editor-content")
    page.keyboard.type("Pozdrav! Lorem ipsum dolor sit amet, consectetur adipiscing elit.")
    page.keyboard.press("Enter")
    page.once("dialog", lambda d: d.accept("Octavia"))
    page.click("text=+ Umetni vozilo")
    page.wait_for_function("document.querySelector('.editor-content table') !== null")
    page.click("form button[type=submit]:has-text('Spremi skicu')")
    page.wait_for_url("**/admin/newsletter/kampanje/*")
    page.click("text=Pošalji testni email meni")
    page.wait_for_load_state()
    page.once("dialog", lambda d: d.accept())
    page.click("form[action$='/posalji'] button")
    page.wait_for_load_state()
    for _ in range(60):  # sending runs in the background (batches of 50)
        page.reload()
        if "Izvještaj" in page.content() and "Šalje se" not in page.content():
            break
        time.sleep(0.5)
    assert "Šalje se" not in page.content(), "kampanja nije poslana"
    run.shot(page, "admin-newsletter-kampanja")

    for path, name in (
        ("/admin/korisnici", "admin-korisnici"),
        ("/admin/statistika?razdoblje=90", "admin-statistika-desktop"),
        ("/admin/postavke", "admin-postavke-desktop"),
        ("/admin/stranice/privatnost", "admin-stranice-editor-desktop"),
        ("/admin/audit", "admin-audit"),
        ("/admin/sustav", "admin-sustav"),
        ("/admin/feed", "admin-feed"),
    ):
        run.goto(page, path)
        run.shot(page, name)
    run.goto(page, "/admin/gdpr")
    page.fill("#g-email", "kupac5@primjer.hr")
    page.click("form.toolbar button[type=submit]")
    page.wait_for_load_state()
    run.shot(page, "admin-gdpr-desktop")

    # Paket Osnovni (nadjačavanje na stranici Sustav): zaključane stavke i stranica 403.
    set_plan_override(page, run, "osnovni")
    run.goto(page, "/admin")
    page.locator(".admin-sidebar, aside").first.screenshot(
        path=str(run.out / "osnovni-izbornik-oznake.png")
    )
    run.shots.append("osnovni-izbornik-oznake.png")
    run.goto(page, "/admin/feed", expect=403)
    run.shot(page, "osnovni-403-paket")
    run.goto(page, "/admin/postavke")
    run.shot(page, "osnovni-postavke")
    set_plan_override(page, run, "")
    ctx.close()

    ctx = browser.new_context(viewport=MOBILE, storage_state=str(state_file))
    page = ctx.new_page()
    run.watch(page)
    for path, name in (
        ("/admin", "admin-dashboard-mobile"),
        ("/admin/vozila", "admin-vozila-mobile"),
        ("/admin/upiti", "admin-upiti-mobile"),
        ("/admin/statistika", "admin-statistika-mobile"),
    ):
        run.goto(page, path)
        run.shot(page, name)
    ctx.close()
    print("[screenshots] admin tijekovi: 2FA, upit, kampanja — OK", flush=True)


def main() -> int:
    ensure_utf8_console()
    parser = argparse.ArgumentParser(description="Screenshotovi i provjera tijekova")
    parser.add_argument("--out", default=str(ROOT / "docs" / "screenshots"))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    tmp = Path(tempfile.mkdtemp(prefix="autokuca-shots-"))
    port = free_port()
    server = start_instance(tmp, port)
    run = Run(f"http://127.0.0.1:{port}", out, tmp / "outbox")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            public_flows(run, browser)
            admin_flows(run, browser, tmp / "admin_state.json")
            browser.close()
    except Exception as exc:  # noqa: BLE001 - report and keep the log
        run.problems.append(f"tijek prekinut: {exc!r}")
    finally:
        server.terminate()
        server.wait(timeout=10)

    print(f"\n[screenshots] {len(run.shots)} slika u {out}:")
    for name in run.shots:
        print("  ", name)
    problems = run.problems + [f"konzola: {line}" for line in run.console]
    if problems:
        print("\n[screenshots] PROBLEMI:")
        for line in problems:
            print("  ✘", line)
        print(f"Log servera: {tmp / 'server.log'}")
        return 1
    shutil.rmtree(tmp, ignore_errors=True)
    print(
        "\n[screenshots] Sve provjere prošle (HTTP statusi, bez horizontalnog skrola, "
        "bez grešaka u konzoli)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
