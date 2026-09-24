#!/usr/bin/env python3
"""
consolidar_resultados_sunat.py

Lee todos los .zip en la carpeta resultados_sunat, extrae los archivos de texto que contienen,
detecta delimitador/encabezado y consolida todo en final_results.csv (utf-8-sig).

Uso:
    python consolidar_resultados_sunat.py
"""

from pathlib import Path
import zipfile
import csv
import io
import sys
import traceback
import pandas as pd

# CONFIG
BASE_DIR = Path(r"C:\Users\P041355\Downloads\archivos_ruc")           # carpeta que contiene resultados_sunat
RESULTS_DIR = BASE_DIR / "resultados_sunat"
OUT_CSV = BASE_DIR / "final_results.csv"
OUT_XLSX = BASE_DIR / "final_results.xlsx"   # opcional, requiere openpyxl instalado
ENCODINGS = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]  # intentos de decodificación

# ---------------------------------------------------------
def try_decode_bytes(b: bytes):
    """Intenta decodificar bytes con varias codificaciones."""
    for enc in ENCODINGS:
        try:
            return b.decode(enc)
        except Exception:
            continue
    # fallback for any remaining
    return b.decode("latin-1", errors="replace")

def sniff_delimiter_and_rows(text: str, max_sample_chars: int = 8192):
    """
    Usa csv.Sniffer para detectar delimitador y si hay header.
    Devuelve (delimiter, has_header, sample_rows_list).
    """
    sample = text[:max_sample_chars]
    # normalize line endings
    sample = sample.replace("\r\n", "\n").replace("\r", "\n")
    # quick heuristic: if '|' appears frequently, prefer it
    if sample.count("|") >= sample.count(",") and sample.count("|") > 0:
        delim = "|"
        has_header = False
        # build rows with csv.reader
        rows = list(csv.reader(io.StringIO(sample), delimiter=delim))
        # heuristica header: if first row has any non numeric tokens / common header words
        first = rows[0] if rows else []
        header_tokens = [t.lower() for t in first]
        header_indicators = any(
            any(k in t for k in ("ruc", "razón", "direccion", "domicilio", "dirección", "estado", "departamento", "provincia", "distrito")) 
            for t in header_tokens
        )
        if header_indicators:
            has_header = True
        return delim, has_header, rows

    # else try csv.Sniffer
    sniffer = csv.Sniffer()
    dialect = None
    try:
        dialect = sniffer.sniff(sample)
        delim = dialect.delimiter
    except Exception:
        # fallback prefer pipe, then comma, then semicolon
        if "|" in sample:
            delim = "|"
        elif ";" in sample:
            delim = ";"
        else:
            delim = ","

    # determine header
    has_header = False
    try:
        has_header = sniffer.has_header(sample)
    except Exception:
        # fallback heuristics
        rows = list(csv.reader(io.StringIO(sample), delimiter=delim))
        first = rows[0] if rows else []
        header_tokens = [t.lower() for t in first]
        header_indicators = any(
            any(k in t for k in ("ruc", "razón", "direccion", "domicilio", "dirección", "estado", "departamento", "provincia", "distrito"))
            for t in header_tokens
        )
        if header_indicators:
            has_header = True

    rows = list(csv.reader(io.StringIO(sample), delimiter=delim))
    return delim, has_header, rows

def parse_text_to_rows(text: str):
    """
    Dado el contenido de un archivo de texto, devuelve lista de dicts (rows) y list de headers.
    """
    # normalizar saltos de linea
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # eliminar líneas vacías al inicio
    lines = [ln for ln in text.split("\n") if ln.strip() != ""]
    if not lines:
        return [], []

    sample = "\n".join(lines[:50])
    delim, has_header, _ = sniff_delimiter_and_rows(sample)

    reader = csv.reader(io.StringIO("\n".join(lines)), delimiter=delim)
    rows = list(reader)

    if not rows:
        return [], []

    # si hay header
    if has_header:
        header = [h.strip() for h in rows[0]]
        data_rows = rows[1:]
    else:
        # si no hay header, generamos col_1..col_n
        maxcols = max(len(r) for r in rows)
        header = [f"col_{i+1}" for i in range(maxcols)]
        data_rows = rows

    dicts = []
    for r in data_rows:
        # pad row to header length
        if len(r) < len(header):
            r = r + [""] * (len(header) - len(r))
        rowd = {header[i]: r[i].strip() for i in range(len(header))}
        # saltar filas vacias (todas las columnas vacías)
        if any(v != "" for v in rowd.values()):
            dicts.append(rowd)
    return dicts, header

# ---------------------------------------------------------
def process_zip_file(zip_path: Path):
    """Abre un zip, procesa cada archivo de texto dentro y devuelve lista de dicts."""
    all_rows = []
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in zf.namelist():
                # ignorar carpetas y archivos no-texto binarios evidentes
                if name.endswith("/"):
                    continue
                # tratar archivos con extensiones txt/csv/rtf/ dat
                lower = name.lower()
                if not (lower.endswith(".txt") or lower.endswith(".csv") or lower.endswith(".dat") or lower.endswith(".rtf")):
                    # intentar leer igualmente como texto si es pequeño
                    pass
                try:
                    b = zf.read(name)
                except Exception:
                    # no se pudo leer, saltar
                    continue
                try:
                    text = try_decode_bytes(b)
                except Exception:
                    text = b.decode("latin-1", errors="replace")

                rows, header = parse_text_to_rows(text)
                if rows:
                    # opcional: añadir metadatos para saber de qué ZIP proviene
                    for r in rows:
                        r["_source_zip"] = zip_path.name
                        r["_source_file_in_zip"] = name
                    all_rows.extend(rows)
    except zipfile.BadZipFile:
        print(f"[WARN] {zip_path.name} no es un ZIP válido, lo ignoro.")
    except Exception as e:
        print(f"[ERROR] al procesar {zip_path.name}: {e}")
        traceback.print_exc()
    return all_rows

def consolidate_all_zips(results_dir: Path):
    zips = sorted([p for p in results_dir.glob("*.zip") if p.is_file()])
    print(f"Encontrados {len(zips)} .zip en {results_dir}")
    total_rows = []
    for z in zips:
        print(f"Procesando {z.name} ...")
        rows = process_zip_file(z)
        print(f"  -> filas extraídas: {len(rows)}")
        total_rows.extend(rows)
    return total_rows

def main():
    if not RESULTS_DIR.exists():
        print(f"Directorio no encontrado: {RESULTS_DIR}")
        sys.exit(1)

    rows = consolidate_all_zips(RESULTS_DIR)
    if not rows:
        print("No se extrajeron filas de los ZIPs. Revisa los archivos en resultados_sunat.")
        sys.exit(0)

    # crear DataFrame guardando columnas en orden consistente
    # tomar la union de todas las claves
    keys = []
    for r in rows:
        for k in r.keys():
            if k not in keys:
                keys.append(k)

    df = pd.DataFrame(rows, columns=keys)
    # Guardar CSV
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"Archivo consolidado guardado en: {OUT_CSV} (filas: {len(df)})")

    # Guardar opcional XLSX (intenta si está instalado)
    try:
        df.to_excel(OUT_XLSX, index=False)
        print(f"También guardado: {OUT_XLSX}")
    except Exception:
        print("openpyxl no está instalado o hubo un error guardando XLSX. Se omitió el XLSX.")

if __name__ == "__main__":
    main()