# Quine Gate reproducibility image (M9, minimal).
#
# Honest scope: this is DIGEST-PINNED, not bit-for-bit reproducible. The base
# image and the code under test are fixed by content, so the offline gate
# suite reproduces identically wherever this image runs — a down payment on
# the "Reproducible Evidence Appliance". The rest of M9 (VM packaging,
# Windows/Linux parity inside a VM, measured boot) stays post-hackathon.
#
#   docker build -t isymotron-quine-gate:v1 .
#   docker run --rm isymotron-quine-gate:v1        # runs the full offline suite

FROM python:3.12-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9

WORKDIR /app
COPY . .
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements-dev.txt

CMD ["python", "-m", "pytest", "-q"]
