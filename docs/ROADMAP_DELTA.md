# Roadmap delta

Where this repository departs from
`IsyMotron — Master Product & Hackathon Roadmap.md` (17 Sep 2026), and why.

The roadmap is good. This file is not a rebuttal; it is the part the roadmap
asks for when it says *"the sequencing is what keeps the ambition from killing
the MVP"* — made specific.

---

## 1. The count

The roadmap's MVP definition (section 25) lists sixteen things the hackathon
submission must show. Counted against what exists today:

| Exists | Does not exist |
|---|---|
| host contract | mobile app (platform 1) |
| L0/L1 boundary | mobile app (platform 2) |
| cross-device workflow *(simulated)* | real Windows 11 host |
| | real Windows 10 host |
| | five real capabilities |
| | Nemotron Intent + Planner |
| | Doctor slow path |
| | sandbox provider |
| | adversarial activity the Doctor catches |
| | marketplace alpha |
| | identity seam |
| | receipts in a UI |
| | Nebius/NVIDIA inference path |

**Thirteen pieces that do not exist have to work at the same time, in about six
weeks, for the MVP as written to be true.** Not sequentially — at the same
time, because the demo runs them in one chain.

That number is the whole argument. Not "is this a good idea" — it is, and the
invariants are unusually well thought through. The question is only which
subset survives contact with a calendar.

## 2. The one thing to do before anything else

The hackathon requires the model to run on specific infrastructure. The roadmap
puts that integration at **M3 (1–4 Oct)**, seventeen days in.

Move it to **day one**, as a throwaway: one Nemotron call through Nebius, timed,
logged, and thrown away. Not the planner — just proof that the account works,
the model id is right, the latency is survivable and the quota is real.

If that fails on 1 October, three weeks of host work becomes a project with no
eligible submission. If it fails today, it costs an afternoon. This is the
cheapest risk reduction available and it is currently scheduled last among the
hard dependencies.

The same applies to the submission deadline itself. The roadmap says *"late
October 2026. Reconfirm exact deadline/time before final week."* That is
currently `UNKNOWN` and every date below is conditional on it.

## 3. What to cut, and what the cut costs

### Cut: the marketplace service

Sections 13 and 20.3 describe a hosted marketplace: publication, reputation,
forks, host-matrix tabs, a gate. That is a product, and it is the one item in
the roadmap with no precedent anywhere in ISyCo.

**Replace with:** a git repository as the registry. An activity is a commit.
The "record" is `activity.json` plus the commit hash. Install = clone at that
hash, verify the tree digest, run the Doctor, write the verdict next to it.

The demo story is *unchanged* — "the marketplace does not distribute trust, it
distributes source plus evidence; your host still decides" is if anything more
literally true with a git remote than with a service. What is lost is the
browsing UI and reputation, neither of which appears in the three-minute demo.

**Saved: roughly M6 in full (14–18 Oct), plus the ongoing cost of running it.**

### Cut: the second mobile platform, and possibly the first

The roadmap spends M2 (25–30 Sep, six days) on a native mobile client and lists
a second platform as MVP item 2.

Native iOS is the highest-cost, lowest-differentiation item on the list, and
ISyCo already has the receipts to prove the cost: `OpencodeNative` exists
because that boundary is hostile. Provisioning, signing and a device in hand
are schedule risk that buys nothing a judge can see, because in a three-minute
video a phone browser and a native app are indistinguishable.

**Replace with:** a responsive web console served by the relay, opened on the
phone. Same screens, same receipts, one codebase, no signing. If time remains
after the core is green, wrap it.

**Saved: most of M2, and all of MVP item 2.**

### Keep, and protect: the Doctor

Everything else in the roadmap is composition. The Doctor is the only piece
that makes the central claim true — *new behaviour may be learned, new
authority may not.* Without it, IsyMotron is a well-specified permission
system, which is good engineering and not a memorable demo.

The demo beat at 0:50–1:35 (an activity asks for admin; the machine proves it
does not need it; it installs with reduced authority) is the single strongest
thing in the whole document. It is also the only moment where the security
model does something *visible* rather than refusing something.

**Do not let the Doctor be the thing that gets compressed at the end.** Build
it after the first real host and before breadth.

### Scope: Windows 10 and Windows 11

Older Windows engines remain useful as contract fixtures, but they are not
product targets. The remaining real-platform work is a Windows 10 host probe;
Windows 98 and other legacy milestones are removed from the roadmap.

## 4. Revised sequence

Same milestones, reordered by what kills the project if it fails.

| When | What | Why here |
|---|---|---|
| **Day 0** | Nebius/Nemotron hello-world, timed | Hard eligibility gate. Fails cheap now, expensive later. |
| **Day 0** | Confirm the Devpost deadline | Every date depends on it. |
| ~~M0~~ | contract freeze | **done** — this repo, 23 tests |
| M1 | real Windows 11 host, 5 capabilities | First contact with a real OS. Expect the path normalizer to be wrong. |
| M2' | web console (not native mobile) | Judges need to see it; phones do not need to run it. |
| M3 | Intent + Planner on the real inference path | The model enters *after* the grammar exists. Non-negotiable. |
| M4 | **Doctor v0 + one sandbox + one adversarial activity** | The thesis. Protect this block. |
| M5 | real Windows 10 host | Proves claim F for the supported Windows 10/11 scope. |
| M6' | git-backed activity registry | Marketplace story at a tenth of the cost. |
| M7' | mock identity provider only | The OIDC seam is a *shape*; one adapter proves it. |
| M8 | reliability numbers | Measured, published as numbers. |
| M9 | breadth, only if green | XP/Vista/10, second platform |
| M11–12 | hardening, submit early | |

## 5. Two invariants the roadmap states but nothing yet enforces

Worth naming so they do not quietly become marketing:

- **2.6 "new authority may not be learned silently"** — currently true because
  nothing can learn anything. It becomes a real claim only when the Doctor and
  the activity installer exist, and it will need a test that *tries* to escalate.
- **2.10 "open source source tree is the primary artifact"** — a policy, not a
  mechanism, until install-from-hash exists.

`docs/EVIDENCE.md` lists both as `NOT_DEMONSTRATED` rather than omitting them.

## 6. The thing worth building even if the hackathon disappears

The roadmap asks for this test, so: if the competition vanished tomorrow, the
part that would still be worth finishing is **the contract plus the Doctor** —
a way to take an unknown piece of executable behaviour, run it in a box, and
produce a scoped, machine-checked statement about what authority it actually
needs rather than what it asks for.

That is useful with zero devices, zero marketplace and zero phones. Everything
else in the document is a distribution strategy for it.
