# -*- coding: utf-8 -*-
"""Profile an FSDB build of CEI charters (read-only).

Answers what the annotation tool has to handle: which charters carry a regest
(cei:abstract) and/or a transcription (cei:tenor), which inline markup occurs
inside those texts, how often names are already marked up, whether diplomatic
parts are encoded, and how this varies per archive. It also picks a stratified
sample of real charters to use as test fixtures.

    python scripts/profile_corpus.py <fsdb-root> <out-dir> [--workers N] [--sample-per-stratum K]

Writes <out-dir>/profile.json and <out-dir>/sample.json. Standard library only.
"""
import argparse
import collections
import hashlib
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from multiprocessing import Pool
from pathlib import Path

CEI = "{http://www.monasterium.net/NS/cei}"
ATOM = "{http://www.w3.org/2005/Atom}"
DIPLOMATIC = ("protocol", "invocatio", "intitulatio", "inscriptio", "arenga", "publicatio", "promulgatio",
              "narratio", "dispositio", "sanctio", "corroboratio", "apprecatio", "eschatocol",
              "authenticationFormula", "datatio", "textBody")
NAMES = ("persName", "placeName", "orgName", "geogName", "issuer", "recipient", "testis", "index")
TEXT_FIELDS = ("abstract", "tenor")


def local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else "#comment"


def text_len(el):
    return len(" ".join("".join(el.itertext()).split()))


def profile_file(path):
    """One charter -> a small dict of facts (no text content kept)."""
    rel = path
    out = {"path": rel, "size": 0, "ok": False}
    try:
        out["size"] = os.path.getsize(path)
        if out["size"] == 0:
            out["error"] = "empty"
            return out
        root = ET.parse(path).getroot()
    except ET.ParseError as e:
        out["error"] = f"parse: {str(e)[:60]}"
        return out
    except OSError as e:
        out["error"] = f"io: {e.__class__.__name__}"
        return out
    out["ok"] = True
    atom = root.find(f"{ATOM}id")
    out["atom_id"] = atom.text.strip() if atom is not None and atom.text else None
    text_el = root.find(f".//{CEI}text")
    out["has_cei_text"] = text_el is not None
    for field in TEXT_FIELDS:
        el = root.find(f".//{CEI}{field}")
        info = {"present": el is not None, "chars": 0, "inline": {}, "names": {}, "diplomatic": [], "attrs": {}}
        if el is not None:
            info["chars"] = text_len(el)
            inline = collections.Counter()
            attrs = collections.Counter()
            for sub in el.iter():
                if sub is el:
                    continue
                name = local(sub.tag)
                inline[name] += 1
                for a in sub.attrib:
                    attrs[f"{name}@{local(a)}"] += 1
            info["inline"] = dict(inline)
            info["attrs"] = dict(attrs)
            info["names"] = {n: inline[n] for n in NAMES if inline.get(n)}
            info["diplomatic"] = sorted(n for n in DIPLOMATIC if inline.get(n))
            info["children"] = [local(c.tag) for c in el][:12]
            info["lang"] = el.get("lang")
        out[field] = info
    # names elsewhere (outside abstract/tenor)
    if text_el is not None:
        back = text_el.find(f"{CEI}back")
        out["back_names"] = sum(1 for e in back.iter() if local(e.tag) in NAMES) if back is not None else 0
        issued = text_el.find(f".//{CEI}issued")
        out["issued_place_filled"] = bool(issued is not None and any(
            (p.text or "").strip() for p in issued.iter(f"{CEI}placeName")))
    out["images"] = sum(1 for _ in root.iter(f"{CEI}graphic"))
    return out


def stratum(fact):
    if not fact["ok"]:
        return "broken"
    a, t = fact.get("abstract", {}), fact.get("tenor", {})
    has_a, has_t = a.get("chars", 0) > 0, t.get("chars", 0) > 0
    if has_t and t.get("diplomatic"):
        return "tenor_diplomatic"
    if has_t and t.get("names"):
        return "tenor_names"
    if has_t and set(t.get("inline", {})) - {"lb", "pTenor", "p"}:
        return "tenor_markup"
    if has_t:
        return "tenor_plain"
    if has_a and a.get("names"):
        return "abstract_names"
    if has_a and a.get("inline"):
        return "abstract_markup"
    if has_a:
        return "abstract_plain"
    return "no_text"


def archive_of(path, root):
    parts = Path(path).relative_to(root).parts
    return parts[1] if parts[0] == "COLLECTIONS" and len(parts) > 3 else parts[0]


def percentile(values, q):
    if not values:
        return 0
    values = sorted(values)
    return values[min(len(values) - 1, int(q * len(values)))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("out")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--sample-per-stratum", type=int, default=4)
    args = ap.parse_args()
    root = Path(args.root).resolve()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    paths = [os.path.join(d, "CH.cei.xml") for d, _, files in os.walk(root) if "CH.cei.xml" in files]
    print(f"found {len(paths)} charters in {time.time() - t0:.0f}s", file=sys.stderr, flush=True)

    totals = collections.Counter()
    strata = collections.Counter()
    errors = collections.Counter()
    per_archive = collections.defaultdict(collections.Counter)
    inline = {f: collections.Counter() for f in TEXT_FIELDS}       # files containing element
    inline_occ = {f: collections.Counter() for f in TEXT_FIELDS}   # total occurrences
    attrs = {f: collections.Counter() for f in TEXT_FIELDS}
    diplomatic = collections.Counter()
    tenor_children = collections.Counter()
    langs = collections.Counter()
    chars = {f: [] for f in TEXT_FIELDS}
    atom_ids = collections.Counter()
    candidates = collections.defaultdict(list)

    with Pool(args.workers) as pool:
        for i, fact in enumerate(pool.imap_unordered(profile_file, paths, chunksize=256), 1):
            if i % 50000 == 0:
                print(f"{i}/{len(paths)} {time.time() - t0:.0f}s", file=sys.stderr, flush=True)
            arch = archive_of(fact["path"], root)
            s = stratum(fact)
            strata[s] += 1
            per_archive[arch][s] += 1
            per_archive[arch]["_total"] += 1
            totals["charters"] += 1
            if not fact["ok"]:
                errors[fact.get("error", "?").split(":")[0]] += 1
                continue
            if fact.get("atom_id"):
                atom_ids[fact["atom_id"]] += 1
            totals["back_names"] += bool(fact.get("back_names"))
            totals["issued_place_filled"] += fact.get("issued_place_filled", False)
            totals["with_images"] += bool(fact.get("images"))
            for f in TEXT_FIELDS:
                info = fact[f]
                if info["chars"]:
                    totals[f"{f}_nonempty"] += 1
                    chars[f].append(info["chars"])
                    if info.get("lang"):
                        langs[f"{f}:{info['lang']}"] += 1
                for name, n in info["inline"].items():
                    inline[f][name] += 1
                    inline_occ[f][name] += n
                for name, n in info["attrs"].items():
                    attrs[f][name] += 1
            for d in fact["tenor"]["diplomatic"]:
                diplomatic[d] += 1
            for c in set(fact["tenor"].get("children", [])):
                tenor_children[c] += 1
            if fact["abstract"]["chars"] and fact["tenor"]["chars"]:
                totals["both_texts"] += 1
            # deterministic pseudo-random candidate ranking per stratum
            key = hashlib.md5(fact["path"].encode()).hexdigest()
            candidates[s].append((key, arch, fact["path"], fact["tenor"]["chars"] + fact["abstract"]["chars"]))

    # stratified sample: up to K per stratum, distinct archives first
    sample = []
    for s, items in sorted(candidates.items()):
        items.sort()
        seen_arch, picked = set(), []
        for key, arch, path, n in items:
            if arch not in seen_arch and n < 20000:
                picked.append({"stratum": s, "archive": arch, "path": str(Path(path).relative_to(root)), "chars": n})
                seen_arch.add(arch)
            if len(picked) >= args.sample_per_stratum:
                break
        sample.extend(picked)
    # plus the longest tenor for stress
    longest = max((c for c in candidates.get("tenor_plain", []) + candidates.get("tenor_names", [])
                   + candidates.get("tenor_markup", []) + candidates.get("tenor_diplomatic", [])),
                  key=lambda c: c[3], default=None)
    if longest:
        sample.append({"stratum": "longest_text", "archive": longest[1],
                       "path": str(Path(longest[2]).relative_to(root)), "chars": longest[3]})

    n = totals["charters"]
    report = {
        "root": str(root),
        "seconds": round(time.time() - t0),
        "charters": n,
        "errors": dict(errors),
        "duplicate_atom_ids": sum(1 for v in atom_ids.values() if v > 1),
        "totals": dict(totals),
        "strata": dict(strata.most_common()),
        "text_chars": {f: {"files": len(v), "p50": percentile(v, .5), "p90": percentile(v, .9),
                           "p99": percentile(v, .99), "max": max(v, default=0)} for f, v in chars.items()},
        "inline_elements": {f: [{"element": k, "files": c, "occurrences": inline_occ[f][k]}
                                for k, c in inline[f].most_common(60)] for f in TEXT_FIELDS},
        "inline_attributes": {f: dict(attrs[f].most_common(40)) for f in TEXT_FIELDS},
        "diplomatic_parts_in_tenor": dict(diplomatic.most_common()),
        "tenor_direct_children": dict(tenor_children.most_common(25)),
        "text_languages": dict(langs.most_common(30)),
        "archives": {a: dict(c) for a, c in sorted(per_archive.items(), key=lambda kv: -kv[1]["_total"])},
    }
    (out / "profile.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "sample.json").write_text(json.dumps(sample, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"done in {report['seconds']}s -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
