"""Compute Krippendorff's alpha (nominal) for the 4-scene blind rating pilot.

Ground truth comes from the fixture file; rater verdicts were produced by two
models that never saw it. Only two raters, four units: alpha is a floor value,
not an estimate with a confidence interval.
"""

import json
import os
from collections import Counter

GROUND_TRUTH = ["PASS", "PASS", "UNDECIDABLE", "FAIL"]

RATERS = {
    "gemini-3.8-flash": ["PASS", "NOT_RUN", "FAIL", "FAIL"],
    "mimo-v2.6-flash": ["UNDECIDABLE", "NOT_RUN", "FAIL", "FAIL"],
}


def krippendorff_alpha_nominal(units):
    """units: list of lists of verdicts, one list per unit (raters must align)."""
    n_raters = len(units[0])
    # observed disagreement
    do_num = 0.0
    do_den = 0.0
    for verdicts in units:
        pairs = 0
        disagree = 0
        for i in range(n_raters):
            for j in range(i + 1, n_raters):
                pairs += 1
                if verdicts[i] != verdicts[j]:
                    disagree += 1
        do_num += disagree
        do_den += pairs
    do = do_num / do_den if do_den else 0.0

    # expected disagreement
    flat = [v for verdicts in units for v in verdicts]
    n = len(flat)
    counts = Counter(flat)
    de_num = sum(c * (c - 1) for c in counts.values())
    de = de_num / (n * (n - 1)) if n > 1 else 0.0

    alpha = 1.0 - (do / de) if de else 1.0
    return do, de, alpha


def main():
    names = list(RATERS)
    units = []
    for idx in range(len(GROUND_TRUTH)):
        units.append([RATERS[name][idx] for name in names])

    do, de, alpha = krippendorff_alpha_nominal(units)

    print("units=%d raters=%d" % (len(units), len(names)))
    print("Do=%.4f  De=%.4f  alpha=%.4f" % (do, de, alpha))
    print()

    print("per-unit verdicts (ground truth first):")
    for i, truth in enumerate(GROUND_TRUTH):
        row = "  scene%d  truth=%-12s" % (i + 1, truth)
        for name in names:
            v = RATERS[name][i]
            row += " %s=%-12s%s" % (name.split("-")[0], v, "" if v == truth else " ✗")
        print(row)

    print()
    for name in names:
        hits = sum(1 for i, v in enumerate(RATERS[name]) if v == GROUND_TRUTH[i])
        print("%s hit %d/%d" % (name, hits, len(GROUND_TRUTH)))

    # where both missed
    print()
    print("both raters missed on:")
    for i, truth in enumerate(GROUND_TRUTH):
        misses = [n for n in names if RATERS[n][i] != truth]
        if len(misses) == len(names):
            print("  scene%d (truth=%s)" % (i + 1, truth))

    out = {
        "units": len(units),
        "raters": names,
        "ground_truth": GROUND_TRUTH,
        "verdicts": RATERS,
        "Do": round(do, 4),
        "De": round(de, 4),
        "alpha": round(alpha, 4),
        "hits": {n: sum(1 for i, v in enumerate(RATERS[n]) if v == GROUND_TRUTH[i]) for n in names},
        "note": "两名盲判、四个单元，alpha 是下界读数，不能当估计值带区间外推。",
    }
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "artifacts", "alpha-pilot.json")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(os.path.abspath(path), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print()
    print("wrote %s" % os.path.abspath(path))


if __name__ == "__main__":
    main()
