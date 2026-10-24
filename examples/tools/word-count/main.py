def run(inputs):
    return {'words': len(inputs['text'].split()), 'characters': len(inputs['text'])}
