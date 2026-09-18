"""The Planner role (L1).

It turns one sentence of human intent into a typed plan of steps. That is all
it does. It cannot execute, cannot grant, cannot widen a scope and cannot
invent a capability: a plan is a *proposal*, and every step still goes through
`Enforcer` on the host before anything happens.

Three properties, each enforced in code rather than asked for in the prompt:

1. **The model only ever sees granted capabilities.** The catalogue comes from
   `host.list_capabilities()`, which omits everything ungranted. The model is
   not told "no"; it is told nothing.
2. **The plan is validated after the fact.** Unknown capability, unknown host,
   undeclared parameter -> `PlanRejected`. A model that hallucinates a step
   produces an error, never a request.
3. **Refusing is a first-class outcome.** When nothing in the catalogue can
   serve the intent, the correct answer is `"steps": []` with a reason, and a
   plan that invents something instead is rejected by (2).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from isymotron.contracts import ExecutionRequest, HostDescription
from isymotron.canon import digest

from .provider import Completion, Provider

SYSTEM = """You are the Planner inside IsyMotron.

You turn a user's request into a JSON plan. You never execute anything and you
have no permissions of your own. A host will independently check every step and
may refuse it.

Reply with ONE JSON object and nothing else:

{
  "understood": "<one short sentence restating the request>",
  "steps": [
    {"host": "<host_id>", "capability": "<capability id>",
     "params": {...}, "why": "<short reason>"}
  ],
  "refused": "<null, or why no plan is possible>"
}

When a step needs a value produced by an EARLIER step, do not describe it in
prose. Use a reference object as the parameter value:

  {"$from": {"step": 1, "field": "content"}}

To build a string from pieces, join literals and references:

  {"$join": ["hostfs://inbox/", {"$from": {"step": 1, "field": "newest_name"}}]}

`step` is 1-based and must be earlier than the step using it. `field` must be
one of the names in that capability's "returns" list -- never a name you guess. The system resolves references before execution; a
placeholder written as ordinary text will be sent literally and is a bug.

Resources are named, never guessed. Each capability lists its "bounds":
- A path is always `hostfs://<root id>/<relative path>`, using a root listed
  in THAT capability's bounds on THAT host, e.g. `hostfs://demo/nota.txt`.
  Never write a drive letter or a physical path; you are not told them.
- An app is always its `id` from the bounds, e.g. `"app": "doom"`.
- To find "the newest/latest/most recent" file, list the root first
  (`filesystem.read` on `hostfs://<id>`) and reference its `newest` field.

Hard rules:
- Use ONLY the capabilities listed in the catalogue below, on the hosts listed.
- Use ONLY the parameter names each capability declares. Never add others.
- Use ONLY the resources named in the bounds. Never invent a root or an app.
- If the catalogue cannot serve the request, return "steps": [] and put the
  reason in "refused". Inventing a capability is a failure, not a fallback.
- Never ask for administrator rights, wider paths, or a shell.
- No prose outside the JSON object."""


class PlanRejected(Exception):
    """The model's output was not a usable plan. Carries why, for the receipt."""

    def __init__(self, reason: str, detail: str = "", raw: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail
        self.raw = raw


@dataclass
class PlanStep:
    host: str
    capability: str
    params: Mapping[str, Any]
    why: str = ""

    def to_dict(self) -> dict:
        return {"host": self.host, "capability": self.capability,
                "params": dict(self.params), "why": self.why}


@dataclass
class Plan:
    understood: str
    steps: list[PlanStep]
    refused: str | None
    plan_id: str
    completion: Completion | None = field(default=None, repr=False)

    def is_refusal(self) -> bool:
        """No steps. Check `refused` to learn whether it said why."""
        return not self.steps

    def verdict(self) -> str:
        """Three classes, never two.

        An empty plan is not a failure: refusing a request the catalogue
        cannot serve is the behaviour we want. Collapsing REFUSED into FAIL
        would have scored our first correct refusal as a bug -- and it did,
        once, before this method existed.
        """
        if self.steps:
            return "PLANNED"
        if self.refused:
            return "REFUSED_WITH_REASON"
        return "EMPTY_NO_REASON"

    def to_dict(self) -> dict:
        d = {
            "plan_id": self.plan_id,
            "understood": self.understood,
            "steps": [s.to_dict() for s in self.steps],
            "refused": self.refused,
        }
        if self.completion is not None:
            d["model"] = self.completion.to_dict()
        return d

    def references(self) -> list[tuple[int, str, int, str]]:
        """Every (step_index, param, source_step, field) this plan depends on."""
        out = []
        for i, s in enumerate(self.steps, 1):
            for key, value in s.params.items():
                for src, field_name in _references_in(value):
                    out.append((i, key, src, field_name))
        return out


class Planner:
    def __init__(self, provider: Provider) -> None:
        self.provider = provider

    # -- catalogue ----------------------------------------------------------
    @staticmethod
    def catalogue(descriptions: Iterable[HostDescription]) -> str:
        """What the model is allowed to know. Granted capabilities only."""
        lines: list[str] = []
        for d in descriptions:
            granted = set(d.granted)
            lines.append(
                f"HOST {d.identity.host_id}  ({d.identity.display_name}, "
                f"{d.identity.os_family} {d.identity.os_release})")
            caps = [c for c in d.capabilities if c.id in granted]
            if not caps:
                lines.append("  (no capabilities granted on this host)")
            for c in caps:
                params = ", ".join(c.params) if c.params else "none"
                lines.append(f"  - {c.id}: {c.summary}")
                lines.append(f"      params: {params}")
                if c.returns:
                    lines.append(f"      returns: {', '.join(c.returns)}")
                # Logical names only. The physical path behind `hostfs://demo`
                # stays on the host; see isymotron/resources.py.
                bounds = (d.bounds or {}).get(c.id)
                if bounds:
                    lines.append(f"      bounds: {json.dumps(bounds, ensure_ascii=False)}")
            lines.append("")
        return "\n".join(lines).rstrip()

    # -- the call -----------------------------------------------------------
    def plan(self, intent: str, descriptions: Sequence[HostDescription],
             max_tokens: int = 900) -> Plan:
        cat = self.catalogue(descriptions)
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"CATALOGUE\n{cat}\n\nREQUEST\n{intent}"},
        ]
        completion = self.provider.complete(messages, max_tokens=max_tokens)
        plan = self.parse(completion.text, descriptions, raw_completion=completion)
        return plan

    # -- validation ---------------------------------------------------------
    @staticmethod
    def parse(text: str, descriptions: Sequence[HostDescription],
              raw_completion: Completion | None = None) -> Plan:
        obj = _extract_json(text)
        if obj is None:
            # Distinguishing these two matters: they have opposite fixes.
            # TRUNCATED means raise max_tokens; NOT_JSON means fix the prompt.
            # On a reasoning model an under-budgeted reply arrives as raw
            # chain-of-thought in `content`, which looks exactly like a model
            # that cannot follow a JSON instruction. It is not.
            if raw_completion is not None and raw_completion.truncated:
                raise PlanRejected(
                    "TRUNCATED",
                    f"finish_reason=length at {raw_completion.completion_tokens} "
                    "output tokens; the budget ran out before the JSON",
                    text)
            raise PlanRejected("NOT_JSON", "no JSON object in the reply", text)
        if not isinstance(obj, dict):
            raise PlanRejected("NOT_AN_OBJECT", type(obj).__name__, text)

        raw_steps = obj.get("steps")
        if raw_steps is None or not isinstance(raw_steps, list):
            raise PlanRejected("NO_STEPS_FIELD", "steps must be a list", text)

        by_host = {d.identity.host_id: d for d in descriptions}
        steps: list[PlanStep] = []
        for i, s in enumerate(raw_steps):
            if not isinstance(s, dict):
                raise PlanRejected("BAD_STEP", f"step {i} is not an object", text)
            host = s.get("host")
            cap = s.get("capability")
            params = s.get("params") or {}
            if not isinstance(params, dict):
                raise PlanRejected("BAD_PARAMS", f"step {i} params is not an object", text)

            desc = by_host.get(host)
            if desc is None:
                raise PlanRejected("UNKNOWN_HOST", f"step {i}: {host!r}", text)
            if cap not in set(desc.granted):
                # Covers both hallucinated capabilities and real ones the model
                # was never shown. Same failure, same message.
                raise PlanRejected("UNKNOWN_CAPABILITY",
                                   f"step {i}: {cap!r} is not in the catalogue for {host}", text)

            manifest = next(c for c in desc.capabilities if c.id == cap)
            undeclared = sorted(set(params) - set(manifest.params))
            if undeclared:
                raise PlanRejected("UNDECLARED_PARAMS",
                                   f"step {i}: {undeclared} on {cap}", text)

            for key, value in params.items():
                try:
                    refs = _references_in(value)
                except ValueError as exc:
                    raise PlanRejected("BAD_REFERENCE",
                                       f"step {i}: params.{key}: {exc}", text)
                for src, field_name in refs:
                    if not isinstance(src, int) or not 1 <= src <= i:
                        # i is 0-based here, so a valid source step is 1..i
                        raise PlanRejected(
                            "BAD_REFERENCE",
                            f"step {i}: params.{key} refers to step {src}, which is "
                            "not an earlier step", text)
                    if not isinstance(field_name, str) or not field_name:
                        raise PlanRejected("BAD_REFERENCE",
                                           f"step {i}: params.{key} has no field name", text)
                    src_step = steps[src - 1]
                    src_desc = by_host[src_step.host]
                    src_manifest = next(c for c in src_desc.capabilities
                                        if c.id == src_step.capability)
                    if src_manifest.returns and field_name not in src_manifest.returns:
                        raise PlanRejected(
                            "UNKNOWN_RESULT_FIELD",
                            f"step {i}: params.{key} reads {field_name!r} from step "
                            f"{src} ({src_step.capability}), which returns "
                            f"{list(src_manifest.returns)}", text)

            steps.append(PlanStep(host=host, capability=cap, params=params,
                                  why=str(s.get("why", ""))))

        refused = obj.get("refused")
        refused = str(refused) if refused not in (None, "", "null") else None
        understood = str(obj.get("understood", "")).strip()

        return Plan(
            understood=understood,
            steps=steps,
            refused=refused,
            plan_id=digest({"understood": understood,
                            "steps": [s.to_dict() for s in steps]}),
            completion=raw_completion,
        )


def _as_reference(value: Any) -> tuple[Any, Any] | None:
    """Is this param value a `{"$from": {"step": n, "field": "k"}}` reference?"""
    if isinstance(value, dict) and "$from" in value:
        ref = value["$from"]
        if isinstance(ref, dict):
            return ref.get("step"), ref.get("field")
        return None, None
    return None


def _as_join(value: Any) -> Any:
    """Is this param value a `{"$join": [part, ...]}`? Returns the parts."""
    if isinstance(value, dict) and "$join" in value:
        return value["$join"]
    return None


def _references_in(value: Any) -> list[tuple[Any, Any]]:
    """Every (step, field) a param value depends on.

    A `$join` composes a string from literals and `$from` references, so a
    plan can build `hostfs://inbox/<name of the newest file>` without a model
    guessing the name. It is validated part by part, exactly like a bare
    reference; anything else inside it is malformed, not ignored.
    """
    ref = _as_reference(value)
    if ref is not None:
        return [ref]
    parts = _as_join(value)
    if parts is None:
        return []
    if not isinstance(parts, list) or not parts:
        raise ValueError("$join takes a non-empty list")
    out = []
    for part in parts:
        if isinstance(part, str):
            continue
        ref = _as_reference(part)
        if ref is None:
            raise ValueError(f"$join parts are strings or $from references, not {part!r}")
        out.append(ref)
    return out


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def _extract_json(text: str) -> Any:
    """Find the JSON object in a reply that may be wrapped or prefaced.

    Reasoning models often emit a fenced block, or a sentence first. We do not
    fight that in the prompt; we parse around it. What we never do is accept a
    partial object -- if it does not parse, it is rejected.
    """
    candidates: list[str] = []
    m = _FENCE.search(text)
    if m:
        candidates.append(m.group(1))
    candidates.append(text)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])

    for c in candidates:
        c = c.strip()
        if not c:
            continue
        try:
            return json.loads(c)
        except ValueError:
            continue
    return None
