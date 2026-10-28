import pytest

from knowledge_line.locales.lt.normalize import normalize
from knowledge_line.locales.lt.numbers import cardinal, date_phrase, ordinal_day, ordinal_year


@pytest.mark.parametrize("n,expected", [
    (0, "nulis"), (1, "vienas"), (12, "dvylika"), (21, "dvidešimt vienas"), (100, "šimtas"),
    (245, "du šimtai keturiasdešimt penki"), (1000, "tūkstantis"), (2026, "du tūkstančiai dvidešimt šeši"),
    (11000, "vienuolika tūkstančių"), (21000, "dvidešimt vienas tūkstantis"),
])
def test_cardinal(n, expected):
    assert cardinal(n) == expected


def test_feminine_and_ordinals():
    assert cardinal(2, feminine=True) == "dvi"
    assert ordinal_day(3) == "trečioji"
    assert ordinal_day(20) == "dvidešimtoji"
    assert ordinal_year(2026) == "du tūkstančiai dvidešimt šeštieji"
    assert date_phrase(2026, 11, 20) == "du tūkstančiai dvidešimt šeštųjų metų lapkričio dvidešimtoji"


@pytest.mark.parametrize("text,expected", [
    ("Skambinkite 112.", "Skambinkite vienas, vienas, du."),
    ("Praneškite ESO telefonu 1852.", "Praneškite e es o telefonu vienas, aštuoni, penki, du."),
    ("Pasiruoškite 72 valandoms.", "Pasiruoškite septyniasdešimt dviem valandoms."),
    ("Būkite pasiruošę 72 valandas.", "Būkite pasiruošę septyniasdešimt dvi valandas."),
    ("Nesiartinkite arčiau kaip 8 metrus.", "Nesiartinkite arčiau kaip aštuonis metrus."),
    ("2–3 dienoms", "dviem ar trims dienoms"),
    ("50 %", "penkiasdešimt procentų"),
    ("14:00", "keturioliktą valandą"),
    ("14:30 val.", "keturiolika valandų trisdešimt minučių"),
    ("žr. lt72.lt", "žiūrėkite el tė septyniasdešimt du taškas el tė"),
    ("PAGD ir BPC", "pė a gė dė ir bė pė cė"),
    ("Taikos g. 245A", "Taikos gatvė du šimtai keturiasdešimt penki A"),
])
def test_normalize(text, expected):
    assert normalize(text) == expected


def test_citations_and_markup_removed():
    assert normalize("**Svarbu** – skambinkite 112 [1].") == "Svarbu – skambinkite vienas, vienas, du ."
