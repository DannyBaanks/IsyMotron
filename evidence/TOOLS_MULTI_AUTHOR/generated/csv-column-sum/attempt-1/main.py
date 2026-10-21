import csv

def run(inputs):
    total = 0
    rows = 0
    with open("/inputs/data.csv", "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += int(row[inputs["column"]])
            rows += 1
    return {"total": total, "rows": rows}
