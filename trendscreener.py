import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FULL_PATH = os.path.join(BASE_DIR, "TEST_full.xlsx")
LATEST_PATH = os.path.join(BASE_DIR, "TEST_latest.xlsx")

# Debug-Ausgaben
print("=== DEBUG ===")
print("Arbeitsverzeichnis:", os.getcwd())
print("BASE_DIR:", BASE_DIR)
print("Dateien vor dem Schreiben:", os.listdir(BASE_DIR))

# Dummy-DataFrame
df = pd.DataFrame({
    "a": [1,2,3],
    "b": [4,5,6]
})

# Schreiben
df.to_excel(FULL_PATH, index=False)
df.tail(2).to_excel(LATEST_PATH, index=False)

print("Dateien nach dem Schreiben:", os.listdir(BASE_DIR))
print("Erwartete Dateien:")
print(" -", FULL_PATH)
print(" -", LATEST_PATH)
print("=== DEBUG ENDE ===")
