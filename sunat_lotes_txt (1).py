from pathlib import Path
import time
import re
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# =========================
# CONFIGURACION
# =========================
INPUT_DIR = Path(r"C:\Users\P041355\Downloads\archivos_ruc")
OUTPUT_DIR = INPUT_DIR / "resultados_sunat"
URL = "https://e-consultaruc.sunat.gob.pe/cl-ti-itmrconsmulruc/jrmS00Alias"

HEADLESS = False
SLOW_MO = 200
PAGE_TIMEOUT = 60000  # ms - timeout para navigation / espera
ZIP_WAIT_TIMEOUT = 60000  # ms - esperar hasta 60s por el zip

# =========================
# UTILIDADES
# =========================
def ensure_dirs():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def extract_number(path: Path):
    m = re.search(r"rucs_(\d+)\.txt$", path.name, re.IGNORECASE)
    return int(m.group(1)) if m else float("inf")

def get_txt_files():
    files = [p for p in INPUT_DIR.glob("*.txt") if p.is_file()]
    return sorted(files, key=extract_number)

def wait_short(page, ms=800):
    page.wait_for_timeout(ms)

def save_debug(page, txt_name: str):
    try:
        page.screenshot(path=str(OUTPUT_DIR / f"{txt_name}.png"), full_page=True)
    except Exception:
        pass
    try:
        (OUTPUT_DIR / f"{txt_name}.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass

# =========================
# SELECTORES Y ACCIONES
# =========================
def open_page(page):
    page.goto(URL, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
    wait_short(page, 1200)

def select_tab_archivo(page):
    # Click en la pestaña "Validar mediante archivo"
    candidates = [
        page.get_by_text("Validar mediante archivo", exact=False),
        page.locator("text=Validar mediante archivo"),
        page.locator("a:has-text('Validar mediante archivo')"),
        page.locator("label:has-text('Validar mediante archivo')"),
    ]
    for loc in candidates:
        try:
            if loc.count() > 0:
                loc.first.click(timeout=5000)
                wait_short(page, 900)
                return True
        except Exception:
            continue
    return False

def upload_txt(page, txt_path: Path):
    file_input = page.locator("input[type='file']")
    if file_input.count() == 0:
        raise RuntimeError("No encontré el selector de archivo (input[type='file']).")
    file_input.first.set_input_files(str(txt_path))
    wait_short(page, 600)

def click_enviar(page):
    """
    Click robusto en el botón <button> Enviar.
    Devuelve True si se realizó el intento de click (no significa resultado OK).
    """
    # Primero intentar localizar botones <button> con texto Enviar
    btns = [
        page.locator("button:has-text('Enviar')"),
        page.get_by_role("button", name="Enviar"),
    ]
    for loc in btns:
        try:
            if loc.count() > 0:
                # usar el primer botón visible
                for i in range(loc.count()):
                    candidate = loc.nth(i)
                    try:
                        if not candidate.is_visible():
                            continue
                        candidate.scroll_into_view_if_needed()
                        wait_short(page, 200)
                        # click normal, con fallback a force
                        try:
                            candidate.click(timeout=5000)
                        except Exception:
                            candidate.click(force=True, timeout=5000)
                        wait_short(page, 500)
                        return True
                    except Exception:
                        continue
        except Exception:
            continue

    # Fallbacks: input[type=submit] con value Enviar
    try:
        inp = page.locator("input[type='submit'][value='Enviar'], input[value='Enviar']")
        if inp.count() > 0:
            inp.first.scroll_into_view_if_needed()
            try:
                inp.first.click(timeout=5000)
            except Exception:
                inp.first.click(force=True, timeout=5000)
            wait_short(page, 500)
            return True
    except Exception:
        pass

    # Si llegamos aquí, no pudimos clicar
    return False

def wait_for_result_link(page, timeout_ms=ZIP_WAIT_TIMEOUT):
    """
    Espera y devuelve el locator del link ZIP resultado (por ejemplo RM....zip).
    Busca texto que termine en .zip o href que contenga .zip.
    """
    deadline = time.time() + (timeout_ms / 1000.0)
    while time.time() < deadline:
        try:
            links = page.locator("a")
            cnt = links.count()
            for i in range(cnt):
                try:
                    text = (links.nth(i).inner_text() or "").strip()
                    href = (links.nth(i).get_attribute("href") or "").strip()
                    # casos: texto termina en .zip o href contiene .zip
                    if text.lower().endswith(".zip") or ".zip" in href.lower():
                        return links.nth(i)
                except Exception:
                    continue
        except Exception:
            pass
        page.wait_for_timeout(800)
    raise RuntimeError("No apareció el link del ZIP resultado dentro del tiempo esperado.")

def download_result_zip(page, txt_path: Path):
    link = wait_for_result_link(page, timeout_ms=ZIP_WAIT_TIMEOUT)
    # intentar descargar con expect_download
    try:
        with page.expect_download(timeout=30000) as dl:
            link.click()
        download = dl.value
        suggested = download.suggested_filename or f"{txt_path.stem}_resultado.zip"
        if not suggested.lower().endswith(".zip"):
            suggested = f"{txt_path.stem}__{suggested}.zip"
        dest = OUTPUT_DIR / f"{txt_path.stem}__{suggested}"
        download.save_as(str(dest))
        return dest
    except PlaywrightTimeoutError:
        # fallback: intentar click sin expect_download y dejar que usuario revise
        try:
            link.click(force=True)
            return None
        except Exception as e:
            raise RuntimeError(f"Fallo al intentar descargar el ZIP: {e}")

def click_retornar(page):
    candidates = [
        page.locator("button:has-text('Retornar')"),
        page.get_by_role("button", name="Retornar"),
        page.locator("input[value='Retornar']"),
    ]
    for loc in candidates:
        try:
            if loc.count() > 0:
                loc.first.click(timeout=5000)
                wait_short(page, 700)
                return True
        except Exception:
            continue
    return False

# =========================
# PROCESO POR ARCHIVO
# =========================
def process_file(page, txt_path: Path):
    print(f"Procesando {txt_path.name}...")
    try:
        open_page(page)
        select_tab_archivo(page)
        upload_txt(page, txt_path)
        wait_short(page, 600)

        clicked = click_enviar(page)
        if clicked:
            print("  Click en 'Enviar' realizado (o intentado). Esperando resultado...")
        else:
            print("  No logré identificar el botón 'Enviar' para clicar. Igual intentaré esperar el resultado...")

        # Esperar y descargar el ZIP resultado
        try:
            downloaded_path = download_result_zip(page, txt_path)
            if downloaded_path:
                print(f"  OK -> Descargado: {downloaded_path.name}")
            else:
                print(f"  OK -> Link de descarga fue activado pero no detecté un archivo descargado automáticamente para {txt_path.name}. Revisa manualmente.")
        except Exception as e:
            raise

        # intentar retornar para seguir con el siguiente lote
        click_retornar(page)
        wait_short(page, 900)
        return True

    except Exception as e:
        print(f"  ERROR -> {txt_path.name}: {e}")
        save_debug(page, txt_path.stem)
        return False

# =========================
# MAIN
# =========================
def main():
    ensure_dirs()
    txt_files = get_txt_files()

    if not txt_files:
        print(f"No encontré archivos .txt en: {INPUT_DIR}")
        return

    print(f"Total de archivos TXT encontrados: {len(txt_files)}")
    print(f"Entrada : {INPUT_DIR}")
    print(f"Salida  : {OUTPUT_DIR}")

    ok = 0
    fail = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=SLOW_MO)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        for txt_path in txt_files:
            result = process_file(page, txt_path)
            if result:
                ok += 1
            else:
                fail += 1
            wait_short(page, 1200)

        browser.close()

    print("\nProceso terminado")
    print(f"Correctos: {ok}")
    print(f"Fallidos : {fail}")
    print(f"Revisa los resultados en: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()