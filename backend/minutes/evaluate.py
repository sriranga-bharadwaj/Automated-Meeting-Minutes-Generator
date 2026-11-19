"""Accuracy evaluation of the minutes generator on labelled transcripts.

Each labelled sample is a pair of files in tests/sample_transcripts/:
    <name>.txt            transcript, one "[HH:MM:SS] text" line per segment
    <name>.expected.json  {"decisions": ["..."],
                           "action_items": [{"task": "...", "owner": "Name" or null,
                                             "deadline": "text" or null}]}

Run from the backend/ folder:
    python -m minutes.evaluate            # runs the model (a few minutes per transcript)
    python -m minutes.evaluate --reuse    # re-scores the saved predictions, no model needed

Writes docs/accuracy_results.json (raw predictions) and docs/accuracy_report.md.
"""
import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(__file__).resolve().parents[1] / "tests" / "sample_transcripts"
DOCS_DIR = REPO_ROOT / "docs"

# The prompt was tuned while looking at these two samples, so scores on them are optimistic.
DEV_SAMPLES = {"meeting_1", "meeting_2"}

TARGET_F1 = 0.75     # Test Plan exit target for action items
STRONG = 0.5         # task-wording overlap that is enough to call two items the same
WEAK = 0.25          # enough when both items have the same (named) owner

STOPWORDS = {
    "a", "an", "the", "for", "and", "or", "to", "of", "in", "on", "at", "by", "it", "is",
    "be", "we", "will", "that", "this", "with", "as", "from", "about", "into", "so",
    "then", "please", "can", "you", "i",
}


# ---------- scoring (pure functions, no model needed) ----------

def _words(text) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in STOPWORDS}


def similarity(a, b) -> float:
    """Overlap coefficient of the content words: 1.0 when the shorter text is contained in the longer."""
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def _norm(owner) -> str:
    return (owner or "").strip().lower()


def same_owner(pred_owner, gold_owner) -> bool:
    return _norm(pred_owner) == _norm(gold_owner)      # None and "" both mean "no owner"


def deadline_ok(pred_deadline, gold_deadline) -> bool:
    if not gold_deadline:
        return not pred_deadline
    return bool(pred_deadline) and gold_deadline.strip().lower() in pred_deadline.strip().lower()


def action_match_score(pred: dict, gold: dict) -> float:
    """Non-zero when the predicted action item is the gold one (task wording, helped by the owner)."""
    s = similarity(pred.get("task"), gold.get("task"))
    if s >= STRONG:
        return s
    if s >= WEAK and _norm(gold.get("owner")) and same_owner(pred.get("owner"), gold.get("owner")):
        return s
    return 0.0


def decision_match_score(pred: str, gold: str) -> float:
    s = similarity(pred, gold)
    return s if s >= STRONG else 0.0


def match(preds: list, golds: list, score_fn) -> list:
    """Greedy one-to-one matching, best scores first. Returns [(pred_index, gold_index), ...]."""
    candidates = []
    for gi, gold in enumerate(golds):
        for pi, pred in enumerate(preds):
            score = score_fn(pred, gold)
            if score > 0:
                candidates.append((score, gi, pi))
    candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
    used_gold, used_pred, pairs = set(), set(), []
    for _score, gi, pi in candidates:
        if gi in used_gold or pi in used_pred:
            continue
        used_gold.add(gi)
        used_pred.add(pi)
        pairs.append((pi, gi))
    return pairs


def prf(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)}


def _ratio(n: int, d: int):
    return round(n / d, 3) if d else None


def _decision_text(d) -> str:
    return d if isinstance(d, str) else (d.get("decision") or d.get("statement") or "")


def score_sample(pred: dict, gold: dict) -> dict:
    """Raw counts for one transcript."""
    p_items = pred.get("action_items", [])
    g_items = gold.get("action_items", [])
    pairs = match(p_items, g_items, action_match_score)
    owner_ok = sum(same_owner(p_items[pi].get("owner"), g_items[gi].get("owner")) for pi, gi in pairs)
    deadline_correct = sum(deadline_ok(p_items[pi].get("deadline"), g_items[gi].get("deadline")) for pi, gi in pairs)

    p_dec = [_decision_text(d) for d in pred.get("decisions", [])]
    g_dec = [_decision_text(d) for d in gold.get("decisions", [])]
    dec_pairs = match(p_dec, g_dec, decision_match_score)

    return {
        "actions": {"pred": len(p_items), "gold": len(g_items), "matched": len(pairs),
                    "owner_ok": owner_ok, "deadline_ok": deadline_correct},
        "decisions": {"pred": len(p_dec), "gold": len(g_dec), "matched": len(dec_pairs)},
    }


def aggregate(scored: list) -> dict:
    """Micro-average over transcripts: counts are added up first, then precision/recall/F1."""
    a = {k: sum(s["actions"][k] for s in scored) for k in ("pred", "gold", "matched", "owner_ok", "deadline_ok")}
    d = {k: sum(s["decisions"][k] for s in scored) for k in ("pred", "gold", "matched")}
    return {
        "transcripts": len(scored),
        "action_detection": prf(a["matched"], a["pred"] - a["matched"], a["gold"] - a["matched"]),
        "action_with_owner": prf(a["owner_ok"], a["pred"] - a["owner_ok"], a["gold"] - a["owner_ok"]),
        "owner_accuracy": _ratio(a["owner_ok"], a["matched"]),
        "deadline_accuracy": _ratio(a["deadline_ok"], a["matched"]),
        "decisions": prf(d["matched"], d["pred"] - d["matched"], d["gold"] - d["matched"]),
    }


# ---------- loading, running, reporting ----------

def load_samples(data_dir: Path) -> list:
    samples = []
    for txt in sorted(data_dir.glob("*.txt")):
        expected = txt.with_suffix(".expected.json")
        if expected.exists():
            samples.append((txt.stem, txt, json.loads(expected.read_text(encoding="utf-8"))))
    return samples


def score_all(samples: list, predictions: dict) -> dict:
    scored = {}
    for name, _txt, gold in samples:
        if name in predictions:
            scored[name] = {"split": "dev" if name in DEV_SAMPLES else "held-out",
                            **score_sample(predictions[name], gold)}
    return scored


def run_model(samples: list, model, results_path: Path) -> dict:
    from .generator import DEFAULT_MODEL, generate_minutes      # lazy: scoring needs no LLM

    model = model or DEFAULT_MODEL
    run = {"model": model, "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
           "predictions": {}, "seconds": {}}
    for i, (name, txt, _gold) in enumerate(samples, start=1):
        print(f"[{i}/{len(samples)}] {name} ...", flush=True)
        start = time.time()
        try:
            prediction = generate_minutes(txt.read_text(encoding="utf-8"), model=model).model_dump()
        except Exception as exc:                  # a failure counts as "found nothing"
            print(f"    FAILED: {exc}", flush=True)
            prediction = {"action_items": [], "decisions": [], "error": str(exc)}
        run["predictions"][name] = prediction
        run["seconds"][name] = round(time.time() - start, 1)
        results_path.write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"    done in {run['seconds'][name]:.0f}s", flush=True)
    return run


def _f(x) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def _met(f1) -> str:
    return "yes" if f1 >= TARGET_F1 else "NO"


def _metrics_table(title: str, scored: list) -> list:
    if not scored:
        return [f"### {title}", "", "No transcripts in this group.", ""]
    agg = aggregate(scored)
    det, own, dec = agg["action_detection"], agg["action_with_owner"], agg["decisions"]
    return [
        f"### {title} ({agg['transcripts']} transcripts)", "",
        "| Metric | Precision | Recall | F1 | Target 0.75 met |",
        "|---|---|---|---|---|",
        f"| Action items: detection (task matched) | {_f(det['precision'])} | {_f(det['recall'])} | {_f(det['f1'])} | {_met(det['f1'])} |",
        f"| Action items: detection and correct owner | {_f(own['precision'])} | {_f(own['recall'])} | {_f(own['f1'])} | {_met(own['f1'])} |",
        f"| Decisions | {_f(dec['precision'])} | {_f(dec['recall'])} | {_f(dec['f1'])} | n/a |",
        "",
        f"Owner accuracy on matched items: {_f(agg['owner_accuracy'])}. "
        f"Deadline accuracy on matched items: {_f(agg['deadline_accuracy'])}.", "",
    ]


def render_report(run: dict, scored: dict) -> str:
    lines = [
        "# Minutes generator: accuracy report", "",
        f"Generated: {run.get('generated', '')}  ",
        f"Model: `{run.get('model', '')}`", "",
        "## Per transcript", "",
        "| Transcript | Split | Gold items | Predicted | Matched | Owner correct | Deadline correct | Decisions matched/gold/predicted | Seconds |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, s in scored.items():
        a, d = s["actions"], s["decisions"]
        secs = run.get("seconds", {}).get(name)
        lines.append(
            f"| {name} | {s['split']} | {a['gold']} | {a['pred']} | {a['matched']} | {a['owner_ok']} "
            f"| {a['deadline_ok']} | {d['matched']}/{d['gold']}/{d['pred']} | {'' if secs is None else round(secs)} |"
        )
    lines += ["", "## Results", ""]
    lines += _metrics_table("Held-out transcripts (the headline result)", [s for s in scored.values() if s["split"] == "held-out"])
    lines += _metrics_table("Development transcripts (the prompt was tuned on these)", [s for s in scored.values() if s["split"] == "dev"])
    lines += _metrics_table("All transcripts", list(scored.values()))
    lines += [
        "## How the scores are computed", "",
        "- A predicted action item matches a labelled one when their task wording overlaps by at least 50 % "
        "(content words, stop words removed), or by at least 25 % when both name the same owner. "
        "Matching is one-to-one.",
        "- Precision = matched / predicted items; recall = matched / labelled items; F1 is their harmonic mean. "
        "Counts are added up over all transcripts before the ratios are taken (micro-average).",
        "- \"Detection and correct owner\" counts a matched item only when the owner is also right "
        "(or both have no owner). Deadline correct means the labelled deadline text appears in the predicted one, "
        "or both are empty.",
        "- Decisions are matched the same way, with the 50 % wording rule.",
        "- The transcripts are clean text, so this measures the minutes generator alone. "
        "Speech-recognition errors are measured separately (word error rate).",
        "- Development transcripts were used while tuning the prompt, so their scores are optimistic. "
        "Quote the held-out result as the accuracy of the system.", "",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Accuracy evaluation of the minutes generator")
    parser.add_argument("--data", type=Path, default=DATA_DIR, help="folder with <name>.txt and <name>.expected.json")
    parser.add_argument("--out", type=Path, default=DOCS_DIR, help="folder for the report (default: docs/)")
    parser.add_argument("--model", default=None, help="Ollama model (default: the module's default)")
    parser.add_argument("--reuse", action="store_true", help="re-score saved predictions without running the model")
    args = parser.parse_args(argv)

    samples = load_samples(args.data)
    if not samples:
        raise SystemExit(f"No labelled transcripts found in {args.data}")
    args.out.mkdir(parents=True, exist_ok=True)
    results_path = args.out / "accuracy_results.json"

    if args.reuse:
        run = json.loads(results_path.read_text(encoding="utf-8"))
    else:
        run = run_model(samples, args.model, results_path)

    scored = score_all(samples, run["predictions"])
    report_path = args.out / "accuracy_report.md"
    report_path.write_text(render_report(run, scored), encoding="utf-8")
    print(f"\nReport written to {report_path}")
    for label, group in (("held-out", "held-out"), ("all", None)):
        subset = [s for s in scored.values() if group is None or s["split"] == group]
        if subset:
            agg = aggregate(subset)
            print(f"{label:>8}: action-item F1 = {agg['action_detection']['f1']:.2f} (detection), "
                  f"{agg['action_with_owner']['f1']:.2f} (with owner)")


if __name__ == "__main__":
    main()