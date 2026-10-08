#!/usr/bin/env python3
"""Summarise a merged Verilator coverage file.

Line and toggle coverage answer different questions and are reported
separately: a wide bus that never sees every bit toggle is normal, while a
basic block that never runs is a hole in the test suite. The unexecuted
lines are listed, because that list is the actionable part.
"""
import collections
import re
import sys

# Records are a sequence of \x01<key>\x02<value> fields followed by a count.
REC = re.compile(r"\x01f\x02([^\x01]*)")
PAGE = re.compile(r"\x01page\x02([^\x01]*)")
LINE = re.compile(r"\x01l\x02([0-9]+)")
OBJ = re.compile(r"\x01o\x02([^\x01]*)")
SPAN = re.compile(r"\x01S\x02([^\x01]*)")


def main(path):
    seen = {}
    for rec in open(path, errors="replace"):
        if not rec.startswith("C "):
            continue
        mf, mp = REC.search(rec), PAGE.search(rec)
        if not (mf and mp):
            continue
        f = mf.group(1).split("/")[-1]
        page = mp.group(1)
        if page.startswith("v_line"):
            kind = "line"
        elif page.startswith("v_branch"):
            kind = "branch"
        else:
            kind = "toggle"
        ml, mo, ms = LINE.search(rec), OBJ.search(rec), SPAN.search(rec)
        key = (f, kind, ml.group(1) if ml else "?",
               (mo.group(1) if mo else "") + "|" + (ms.group(1) if ms else ""))
        try:
            cnt = int(rec.rsplit(" ", 1)[1])
        except ValueError:
            continue
        # the same point appears once per testbench instance: sum the hits
        seen[key] = seen.get(key, 0) + cnt

    tot, hit = collections.Counter(), collections.Counter()
    for (f, kind, _l, _o), c in seen.items():
        tot[(f, kind)] += 1
        if c:
            hit[(f, kind)] += 1

    kinds = ("line", "branch", "toggle")
    print("%-18s %14s %14s %14s" % (("file",) + kinds))
    sums = {k: [0, 0] for k in kinds}
    for f in sorted({k[0] for k in tot}):
        if not f.startswith("npu"):
            continue
        row = "%-18s" % f
        for k in kinds:
            t, h = tot[(f, k)], hit[(f, k)]
            sums[k][0] += t
            sums[k][1] += h
            row += " %5d/%-4d %3d%%" % (h, t, 100 * h // t if t else 0)
        print(row)
    row = "%-18s" % "TOTAL"
    for k in kinds:
        t, h = sums[k]
        row += " %5d/%-4d %3d%%" % (h, t, 100 * h // t if t else 0)
    print(row)

    misses = collections.defaultdict(set)
    for (f, kind, l, _o), c in seen.items():
        if kind in ("line", "branch") and c == 0 and f.startswith("npu"):
            misses[f].add(int(l))
    if misses:
        print("\nunexecuted lines / untaken branches:")
        for f in sorted(misses):
            print("  %-18s %s" % (f, " ".join(str(x) for x in sorted(misses[f]))))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "build/cov/all.dat")
