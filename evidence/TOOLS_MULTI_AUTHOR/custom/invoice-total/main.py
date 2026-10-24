def run(inputs):
    lines = inputs['lines']
    return {
        'total_cents': sum(line['quantity'] * line['unit_cents'] for line in lines),
        'items': len(lines),
    }
