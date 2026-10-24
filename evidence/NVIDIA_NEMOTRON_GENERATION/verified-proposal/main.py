import re

def run(_inputs):
    with open("/inputs/contacts.txt", "r") as f:
        text = f.read()
    emails = re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    unique_sorted = sorted(set(emails))
    return {"emails": unique_sorted}
