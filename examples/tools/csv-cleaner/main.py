import csv, json

def run(inputs):
    with open('/inputs/data.csv', newline='') as source:
        reader = csv.DictReader(source)
        columns = [column.strip() for column in reader.fieldnames or []]
        rows = [{str(key).strip(): value.strip() for key, value in row.items()} for row in reader]
    report = {'columns': columns, 'records': rows, 'rows': len(rows)}
    with open('report.json', 'w') as output:
        json.dump(report, output, ensure_ascii=False)
    return {'rows': len(rows)}
