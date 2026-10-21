import unicodedata

def run(inputs):
    text = inputs["text"]
    normalized = unicodedata.normalize('NFKD', text)
    ascii_bytes = normalized.encode('ascii', 'ignore')
    ascii_str = ascii_bytes.decode('ascii')
    lower = ascii_str.lower()
    import re
    slug = re.sub(r'[^a-z0-9]+', '-', lower)
    slug = slug.strip('-')
    return {"slug": slug}
