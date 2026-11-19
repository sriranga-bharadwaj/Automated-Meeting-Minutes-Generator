import json

from minutes.evaluate import (
    action_match_score,
    aggregate,
    deadline_ok,
    load_samples,
    main,
    match,
    prf,
    render_report,
    same_owner,
    score_all,
    score_sample,
    similarity,
)


def action(task, owner=None, deadline=None):
    return {"task": task, "owner": owner, "deadline": deadline}


GOLD_1 = {
    "decisions": ["Use a pre-recorded five minute meeting for the demo instead of a live recording"],
    "action_items": [
        action("Finish the minutes editor screen", "Ravi", "Wednesday"),
        action("Split long audio into chunks to speed up transcription", "Priya", None),
        action("Record the sample meeting and send it to Priya", "Meera", "Monday"),
        action("Write the README", None, "submission"),
    ],
}


def perfect_prediction():
    return {
        "decisions": [{"decision": "Use a pre-recorded five-minute meeting for the demo", "context": None}],
        "action_items": [
            action("Finish the minutes editor by Wednesday", "Ravi", "Wednesday"),
            action("Split longer audio recordings into chunks", "Priya", None),
            action("Record a sample meeting", "Meera", "Monday"),
            action("Write the README", None, "before submission"),
        ],
    }


def test_similarity_basics():
    assert similarity("Write the README", "write the readme") == 1.0
    assert similarity("Write the README", "Book the meeting room") == 0.0
    assert similarity("", "anything") == 0.0
    assert similarity("Fix the bug", "Fix the refund bug on the checkout page") == 1.0   # contained


def test_owner_and_deadline_rules():
    assert same_owner(None, "") and same_owner("Ravi", "ravi") and not same_owner("Ravi", None)
    assert deadline_ok(None, None) and deadline_ok("", None)
    assert not deadline_ok("Friday", None)
    assert deadline_ok("before the review on Thursday", "review")
    assert not deadline_ok(None, "Monday") and not deadline_ok("Tuesday", "Monday")


def test_paraphrase_with_the_same_owner_matches():
    pred = action("Swap out the images", "Anita")
    gold = action("Replace the placeholder images on the pricing page", "Anita")
    assert action_match_score(pred, gold) > 0


def test_paraphrase_without_an_owner_does_not_match():
    pred = action("Swap out the images", None)
    gold = action("Replace the placeholder images on the pricing page", None)
    assert action_match_score(pred, gold) == 0.0


def test_unrelated_items_with_the_same_owner_do_not_match():
    assert action_match_score(action("Book the meeting room", "Dev"),
                              action("Fix the refund bug", "Dev")) == 0.0


def test_matching_is_one_to_one():
    golds = [action("Write the README"), action("Write the README file")]
    preds = [action("Write the README")]
    assert len(match(preds, golds, action_match_score)) == 1


def test_perfect_prediction_scores_one():
    s = score_sample(perfect_prediction(), GOLD_1)
    agg = aggregate([s])
    assert agg["action_detection"]["f1"] == 1.0
    assert agg["action_with_owner"]["f1"] == 1.0
    assert agg["owner_accuracy"] == 1.0 and agg["deadline_accuracy"] == 1.0
    assert agg["decisions"]["f1"] == 1.0


def test_missing_item_lowers_recall_only():
    pred = perfect_prediction()
    pred["action_items"].pop(1)
    det = aggregate([score_sample(pred, GOLD_1)])["action_detection"]
    assert det["precision"] == 1.0 and det["recall"] == 0.75


def test_extra_item_lowers_precision_only():
    pred = perfect_prediction()
    pred["action_items"].append(action("Plan the offsite", "Zoya"))
    det = aggregate([score_sample(pred, GOLD_1)])["action_detection"]
    assert det["recall"] == 1.0 and det["precision"] == 0.8


def test_wrong_owner_is_found_but_not_counted_with_owner():
    pred = perfect_prediction()
    pred["action_items"][0]["owner"] = None
    agg = aggregate([score_sample(pred, GOLD_1)])
    assert agg["action_detection"]["f1"] == 1.0
    assert agg["action_with_owner"]["recall"] == 0.75
    assert agg["owner_accuracy"] == 0.75


def test_empty_prediction_scores_zero():
    agg = aggregate([score_sample({"action_items": [], "decisions": []}, GOLD_1)])
    assert agg["action_detection"]["f1"] == 0.0
    assert agg["owner_accuracy"] is None


def test_micro_average_adds_counts_before_dividing():
    big = {"action_items": [action(f"Task number {i} alpha", f"P{i}") for i in range(9)], "decisions": []}
    small_gold = {"action_items": [action("Write the README")], "decisions": []}
    small_pred = {"action_items": [], "decisions": []}
    scored = [score_sample(big, big), score_sample(small_pred, small_gold)]
    det = aggregate(scored)["action_detection"]
    assert (det["tp"], det["fp"], det["fn"]) == (9, 0, 1)
    assert det["recall"] == 0.9


def test_prf_handles_zero_denominators():
    assert prf(0, 0, 0)["f1"] == 0.0


def test_pipeline_with_files(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    for name in ("meeting_1", "extra_1"):
        (data / f"{name}.txt").write_text("[00:00:01] hello", encoding="utf-8")
        (data / f"{name}.expected.json").write_text(json.dumps(GOLD_1), encoding="utf-8")
    (data / "unlabelled.txt").write_text("no labels", encoding="utf-8")

    samples = load_samples(data)
    assert [s[0] for s in samples] == ["extra_1", "meeting_1"]          # unlabelled one is skipped

    run = {"model": "fake", "generated": "now", "seconds": {"meeting_1": 12.0},
           "predictions": {"meeting_1": perfect_prediction(), "extra_1": {"action_items": [], "decisions": []}}}
    scored = score_all(samples, run["predictions"])
    assert scored["meeting_1"]["split"] == "dev" and scored["extra_1"]["split"] == "held-out"

    report = render_report(run, scored)
    assert "Held-out transcripts" in report and "Target 0.75 met" in report

    out = tmp_path / "out"
    out.mkdir()
    (out / "accuracy_results.json").write_text(json.dumps(run), encoding="utf-8")
    main(["--data", str(data), "--out", str(out), "--reuse"])           # no model is called
    assert (out / "accuracy_report.md").read_text(encoding="utf-8").startswith("# Minutes generator")