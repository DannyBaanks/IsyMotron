# Product thesis

## One sentence

IsyMotron is a personal AI capability fabric in which a model can compose
explicitly granted capabilities across a user's phones and computers, and in
which new behaviour can be learned and shared, but new authority cannot.

## The asymmetry the product is built on

Everything else follows from one sentence:

> **New behaviour may be learned. New authority may not be learned silently.**

A model that gets better at doing things is useful. A model that gets better at
being allowed to do things is a security incident. The product's job is to make
the first cheap and the second structurally impossible.

## What it is not

- Not a remote desktop. Nothing here streams pixels or forwards input.
- Not a chatbot with a shell. There is no unrestricted shell capability, and
  adding one would be a contract change, not a feature.
- Not a plugin store. Distributing an opaque archive and asking the user to
  trust it is the thing this product exists to replace.

## The invariants

These are rules about the code, not slogans. Where the code enforces one, the
file and function are named.

| # | Invariant | Enforced where |
|---|---|---|
| 1 | Capability != implementation. The contract is stable; the engine is local. | `hosts/simulator/engines.py` — two engines, one contract |
| 2 | Host != operating system. A host is a participation surface. | `core/isymotron/host.py:Host` |
| 3 | Transport != contract. Replace the relay and nothing else notices. | `relay/loopback.py` holds no policy |
| 4 | The model interprets; the mechanism enforces. | `core/isymotron/policy.py:Enforcer` is pure and model-free |
| 5 | No capability means no action. | `Host.list_capabilities` omits ungranted ids |
| 6 | New behaviour may be learned; new authority may not. | Doctor V0 + Python sandbox demonstrate this in a scoped provider |
| 7 | Local authority always wins. | `Host.request_lease` intersects, never unions |
| 8 | Verification is scoped, never universal. | `DoctorVerdict` has no `SAFE` member |
| 9 | A changed artifact is a new trust problem. | `core/isymotron/marketplace.py:GitActivityRegistry.install` rejects tree digest changes |
| 10 | Source is the primary artifact, not a binary bundle. | Git-backed activity registry installs source at a pinned commit |
| 11 | Doctor evidence is machine evidence. | Doctor V0 seals reports; provider integration pending |
| 12 | An external reviewer model is advisory, never authority. | `Decision` is produced only by `Enforcer` |
| 13 | Unsupported != impossible. | scope statement, not a technical claim |

Invariants 6, 9, 10 and 11 are currently **claims about the design**, not about
the code. They are listed so the gap is visible rather than implied.

## Why the authority grammar comes before the model

The roadmap puts model integration at step 11 of 11, and this repo follows that
literally: there is no Nemotron call anywhere in it yet.

The reason is not caution, it is architecture. If a planner is wired in before
the grammar of leases, scopes and receipts exists, the planner's prompt becomes
the place where authority is decided — because it is the only place where the
question is being asked. After that point, every security property of the
product is a property of a prompt. That is not recoverable by adding a policy
engine later; by then the rest of the system is shaped around the model's
answer.

So M0 builds the thing the model will not be allowed to touch, first.

## What "personal" means here

The user's devices are not managed endpoints and IsyMotron is not an MDM. A
host participates because someone sat at that machine and granted a capability
with a scope. That grant lives on the device. No cloud record, marketplace
badge, reviewer model or prior receipt can widen it.

This is why `Host.request_lease` intersects the requested scope with the local
grant and silently drops the rest: asking for more is always safe to attempt
and never succeeds.
