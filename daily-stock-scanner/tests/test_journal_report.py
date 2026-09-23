"""Journal chaîné, suivi de performance, rendu du rapport et pipeline de bout en bout."""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from scanner.journal.journal import GENESIS, Journal, JournalError
from scanner.journal.performance import evaluate_entries, summarize_performance
from scanner.report.render import fmt_value


def _rec(sym, side="long"):
    return {
        "as_of": "2024-01-02T00:00:00+00:00",
        "book": "M",
        "side": side,
        "rank": 1,
        "symbol": sym,
        "score": 1.0,
    }


def test_journal_chain_and_tamper_detection(tmp_path):
    j = Journal(tmp_path / "journal.jsonl")
    assert j.head() == (GENESIS, 0)
    head1, n1 = j.append([_rec("A.US"), _rec("B.US")])
    head2, n2 = j.append([_rec("C.US")])
    assert (n1, n2) == (2, 3) and head1 != head2
    assert j.verify() == (True, 3, None)
    # falsification d'une recommandation passée
    lines = (tmp_path / "journal.jsonl").read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[1])
    entry["symbol"] = "Z.US"
    lines[1] = json.dumps(entry)
    (tmp_path / "journal.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, _, problem = j.verify()
    assert not ok and "ligne 2" in problem
    with pytest.raises(JournalError):
        j.append([_rec("D.US")])


def test_journal_deletion_is_detected(tmp_path):
    j = Journal(tmp_path / "journal.jsonl")
    j.append([_rec("A.US"), _rec("B.US"), _rec("C.US")])
    lines = (tmp_path / "journal.jsonl").read_text(encoding="utf-8").splitlines()
    del lines[1]
    (tmp_path / "journal.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert not j.verify()[0]


def test_commitment_contains_head(tmp_path):
    j = Journal(tmp_path / "journal.jsonl")
    head, _ = j.append([_rec("A.US")])
    path = j.write_commitment("2024-01-02", tmp_path / "commitments", {"config": "x"})
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["journal_head_sha256"] == head and payload["entries"] == 1


def test_performance_uses_next_open_and_signs_shorts():
    idx = pd.bdate_range("2024-01-01", periods=10)
    close = pd.DataFrame({"A.US": np.linspace(100, 109, 10), "B.US": 100.0}, index=idx)
    opn = close - 0.5
    entries = pd.DataFrame([{**_rec("A.US"), "seq": 1}, {**_rec("A.US", "short"), "seq": 2}])
    ev = evaluate_entries(entries, opn, close, [5])
    ref = opn.loc["2024-01-02", "A.US"]  # première séance >= date de décision : ouverture
    expected = close["A.US"].iloc[1 + 5] / ref - 1
    assert ev.iloc[0]["ret_5d"] == pytest.approx(expected)
    assert ev.iloc[1]["ret_5d"] == pytest.approx(-expected)
    summary = summarize_performance(ev, [5])
    assert set(summary["side"]) == {"long", "short"}


def test_value_formatting():
    assert fmt_value("Q-MOM-12-1", 0.2346) == "+23.5 %"
    assert fmt_value("F-PIOT", 7.0) == "7.00 / 9"
    assert fmt_value("Q-52WH", 0.9) == "90 % du plus haut"
    assert fmt_value("F-GP", float("nan")) == "n.d."


def test_demo_pipeline_end_to_end(config, tmp_path):
    from scanner.pipeline.demo import run_demo

    res = run_demo(config, tmp_path, days=(date(2026, 9, 22), date(2026, 9, 23)), n_securities=120)
    assert len(res.daily) == 2
    md = res.daily[1].report_md.read_text(encoding="utf-8")
    html = res.daily[1].report_html.read_text(encoding="utf-8")
    assert "DÉMONSTRATION SUR DONNÉES SYNTHÉTIQUES" in md
    assert "Livre S" in md and "Livre M" in md and "Livre L" in md
    assert "Changements par rapport à la veille" in md
    assert "<html" in html and "Scanner quotidien" in html
    j = Journal(tmp_path / "journal" / "journal.jsonl")
    ok, n, _ = j.verify()
    assert ok and n == 2 * len(res.daily[0].ideas)
    commitment = json.loads(res.daily[1].commitment.read_text(encoding="utf-8"))
    assert commitment["entries"] == n and commitment["demo"] is True
