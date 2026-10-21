import json


def run(inputs):
    with open('/inputs/data.json', 'r', encoding='utf-8') as source:
        data = json.load(source)
    if not isinstance(data, dict):
        raise ValueError('expected a JSON object')
    with open('pretty.json', 'w', encoding='utf-8') as output:
        json.dump(data, output, indent=2, sort_keys=True, ensure_ascii=False)
        output.write('\n')
    return {'keys': len(data)}
