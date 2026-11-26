"""match_graph: one-to-many lists (names only) join the other sources."""
import pandas as pd

from sg.genetics import match_graph as mg


def test_by_id_names_to_known_ids_only():
    df = pd.DataFrame({"match_key": ["name:anna example", "name:bo nobody", "D-1"],
                       "match": ["Anna Example", "Bo Nobody", "Cia Listed"]})
    out = mg.by_id(df, {mg.icw_io.name_key("Anna Example"): "D-9"})
    # known name -> its ID; unknown keeps the name key; an ID stays
    assert out.match_key.tolist() == ["D-9", "name:bo nobody", "D-1"]


def test_one_per_donor_keeps_the_stronger_group():
    full, sel = "MyHeritage", "MyHeritage (selection 2026-01-01 1)"
    placed = pd.DataFrame({"match_key": ["D-9", "D-9", "D-9"], "subject": ["a", "a", "b"],
                           "platform": [full, sel, sel], "placed_cM": [20.0, 80.0, 50.0]})
    segs = pd.DataFrame({"match_key": ["D-9"] * 4, "subject": ["a", "a", "a", "b"],
                         "platform": [full, sel, sel, sel], "match": ["Anna"] * 4,
                         "cM": [20.0, 50.0, 30.0, 50.0]})
    p, s = mg.one_per_donor(placed, segs)
    assert sorted(zip(p.subject, p.platform)) == [("a", sel), ("b", sel)]
    # donor a's evidence counted once, from the selection
    assert s.groupby("subject").cM.sum().to_dict() == {"a": 80.0, "b": 50.0}
