from knowledge_line.locales.lt.stem import stem
from knowledge_line.rag.places import PlaceIndex, Shelter


def test_inflections_share_stem():
    assert stem("Žirmūnuose") == stem("Žirmūnų") == stem("Žirmūnai")
    assert stem("Vilniuje") == stem("Vilniaus") == stem("Vilnius")
    assert stem("priedangą") == stem("priedangos")


def test_place_match_from_locative():
    idx = PlaceIndex([
        Shelter("Vilniaus m. sav.", "Žirmūnų", "Vilnius", "Kalvarijų g.", "1", "Požeminė aikštelė", "300"),
        Shelter("Vilniaus m. sav.", "Žirmūnų", "Vilnius", "Žirmūnų g.", "5", "Rūsys", "80"),
        Shelter("Kauno m. sav.", "Centro", "Kaunas", "Laisvės al.", "2", "Garažai", "50"),
    ])
    m = idx.match("Kur slėptis? Gyvenu Žirmūnuose.")
    assert m and m.eldership == "Žirmūnų" and m.municipality == "Vilniaus m. sav."
    assert m.shelters[0].capacity == "300"  # largest first
    assert idx.match("Kur slėptis per oro pavojų?") is None
