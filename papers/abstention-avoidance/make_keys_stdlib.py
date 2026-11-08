"""Generate answer keys with the standard library only.

Deliberately imports nothing from the project: the point is that the key
generator shares no module with the judge runner, so a bug in the runner
cannot silently shape the keys.

Usage:
  python tools/make_keys_stdlib.py            # writes artifacts/keys/*.json
"""

import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.abspath(os.path.join(HERE, ".."))
ART = os.path.join(WS, "artifacts")
KEYS = os.path.join(ART, "keys")

FIXTURES = ["ncp-fixture-scale8.json", "ncp-fixture-adv8.json",
            "ncp-fixture-hardset8.json", "ncp-fixture-hardset8-v2.json",
            "ncp-fixture-hardset8-v3.json", "ncp-fixture-hardset8-v4.json",
            "ncp-fixture-12scene.json", "ncp-fixture-goodset6.json",
            "ncp-fixture-holdout6.json"]


def key_of(fixture):
    scenes = fixture.get("scenes") or []
    answers = {}
    for sc in scenes:
        sid = sc.get("id")
        exp = sc.get("expected")
        if sid is None or exp is None:
            continue
        answers[str(sid)] = exp
    counts = {}
    for v in answers.values():
        counts[v] = counts.get(v, 0) + 1
    return {"fixture_id": fixture.get("fixture_id", ""),
            "units": len(answers),
            "answers": answers,
            "distribution": counts}


def main():
    os.makedirs(KEYS, exist_ok=True)
    written = 0
    for name in FIXTURES:
        path = os.path.join(ART, name)
        if not os.path.exists(path):
            continue
        with io.open(path, encoding="utf-8") as fh:
            fx = json.load(fh)
        key = key_of(fx)
        if not key["answers"]:
            continue
        out = os.path.join(KEYS, name.replace("ncp-fixture-", "").replace(".json", "") + "-key.json")
        with io.open(out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(key, fh, ensure_ascii=False, indent=1)
        written += 1
        print("%-40s %d 格  %s" % (name, key["units"], key["distribution"]))
    print("written:", written, "->", KEYS)


if __name__ == "__main__":
    main()
