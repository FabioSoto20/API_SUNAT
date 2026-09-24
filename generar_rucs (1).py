import pandas as pd
import os
import math

# 📂 Archivo de entrada
archivo_csv = r'C:\Users\P041355\Downloads\base_ruc.csv'  # cambia si tu archivo tiene otro nombre

# 📁 Carpeta de salida
carpeta_salida = r'C:\Users\P041355\Downloads\archivos_ruc'
os.makedirs(carpeta_salida, exist_ok=True)

# 🔢 Tamaño máximo por archivo
tamano_lote = 100

# 📊 Leer CSV
df = pd.read_csv(archivo_csv, dtype=str)

# Validar columna
if "RUC" not in df.columns:
    raise ValueError("El archivo CSV debe tener una columna llamada 'RUC'")

# Limpiar datos
rucs = df["RUC"].dropna().astype(str).str.strip().tolist()

# 📦 Calcular número de archivos
num_archivos = math.ceil(len(rucs) / tamano_lote)

print(f"Total RUCs: {len(rucs)}")
print(f"Archivos a generar: {num_archivos}")

# 📝 Generar archivos
for i in range(num_archivos):
    inicio = i * tamano_lote
    fin = inicio + tamano_lote
    lote = rucs[inicio:fin]

    nombre_archivo = os.path.join(carpeta_salida, f"rucs_{i+1}.txt")

    with open(nombre_archivo, "w") as f:
        for ruc in lote:
            f.write(f"{ruc}|\n")

print("✅ Archivos generados correctamente.")