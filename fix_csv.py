import csv
from pathlib import Path

# Укажи имя исходного файла
input_file = Path("boq_export_building_16160-13.csv")
output_file = Path("boq_clean.csv")

# Если у тебя имя файла немного другое, просто замени строку выше
# на точное имя твоего CSV-файла.

rows = []

with open(input_file, "r", encoding="utf-8", newline="") as f:
    sample = f.read(4096)
    f.seek(0)

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;")
    except csv.Error:
        class SimpleDialect(csv.Dialect):
            delimiter = ","
            quotechar = '"'
            escapechar = None
            doublequote = True
            skipinitialspace = False
            lineterminator = "\n"
            quoting = csv.QUOTE_MINIMAL
        dialect = SimpleDialect

    reader = csv.reader(f, dialect)

    for row in reader:
        cleaned_row = []
        for cell in row:
            if isinstance(cell, str):
                cell = cell.replace("\r", " ").replace("\n", " ").strip()
                cell = " ".join(cell.split())
            cleaned_row.append(cell)
        rows.append(cleaned_row)

if not rows:
    raise ValueError("Файл пустой или не удалось прочитать данные.")

# Выравниваем строки по длине заголовка
header_len = len(rows[0])
fixed_rows = [rows[0]]

for row in rows[1:]:
    if len(row) < header_len:
        row = row + [""] * (header_len - len(row))
    elif len(row) > header_len:
        row = row[:header_len]
    fixed_rows.append(row)

with open(output_file, "w", encoding="utf-8", newline="") as f:
    writer = csv.writer(f, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL)
    writer.writerows(fixed_rows)

print("Готово.")
print(f"Создан файл: {output_file.resolve()}")