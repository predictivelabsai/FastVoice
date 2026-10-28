# Scripted demo run

Providers: LLM `gemini:gemini-2.5-flash`, STT `elevenlabs`, TTS `elevenlabs`; KB chunks 48, shelters 6584; phone channel: True

## A1-shelter-eldership – Priedangos (su seniūnija) ir prašymas kalbėti lėčiau

**Sistema:** Sveiki, skambinate į civilinės saugos informacijos liniją. Jus aptarnauja dirbtinio intelekto sistema, ne žmogus. Teikiama informacija yra informacinio pobūdžio. Jei kyla pavojus gyvybei ar sveikatai, skambinkite 112. Jei norite, kad kalbėčiau lėčiau, pasakykite „lėčiau“ arba paspauskite 1. Kuo galiu padėti?

**Skambintojas:** Laba diena, kur man slėptis, jei paskelbtų oro pavojų? Gyvenu Žirmūnuose.

*STT atpažino:* Laba diena, kur man slėptis, jei paskelbtų oro pavojų? Gyvenu Žirmūnuose.

**Sistema** (`answer`): Ar teisingai supratau – Žirmūnų seniūnija (Vilniaus m. sav.)? Oro pavojaus atveju Jums rekomenduojama vykti į artimiausią priedangą [2]. Žirmūnų seniūnijoje yra dvi priedangos: daugiabutis namas su požeminiu parkingu Verkių g. 39 ir daugiabutis namas su požeminiu parkingu Olimpiečių g. 3E [1]. Abi priedangos pritaikytos asmenims su negalia [1].

Jei priedangos nėra šalia, slėpkitės kitoje saugioje vietoje, pavyzdžiui, namo rūsyje arba vidinėje patalpoje be langų, atitinkančioje dviejų sienų taisyklę [2, 3]. Venkite langų, balkonų, liftų ir atvirų erdvių, o patalpos paskutiniame aukšte netinka [3].

Šaltiniai: [1] PAGD priedangų sąrašas (atvirieji duomenys, data.gov.lt) – https://get.data.gov.lt/datasets/gov/pagd/priedangos/Priedanga; [2] Priedangos – https://lt72.lt/priedangos-2-3/; [3] Oro pavojus: ką svarbu žinoti? – https://lt72.lt/rekomendacijos-oro-pavojaus-atveju/

Delsa (ms): `{"retrieval": 2.4, "llm": 1297.2, "total_text": 1301.7, "stt": 1669.6, "tts": 4782.5}`

**Skambintojas:** Pakartokite, prašau, lėčiau.

*STT atpažino:* Pakartokite, prašau, lėčiau

**Sistema** (`repeat`): Pakartosiu lėčiau. Ar teisingai supratau – Žirmūnų seniūnija (Vilniaus m. sav.)? Oro pavojaus atveju Jums rekomenduojama vykti į artimiausią priedangą [2]. Žirmūnų seniūnijoje yra dvi priedangos: daugiabutis namas su požeminiu parkingu Verkių g. 39 ir daugiabutis namas su požeminiu parkingu Olimpiečių g. 3E [1]. Abi priedangos pritaikytos asmenims su negalia [1].

Jei priedangos nėra šalia, slėpkitės kitoje saugioje vietoje, pavyzdžiui, namo rūsyje arba vidinėje patalpoje be langų, atitinkančioje dviejų sienų taisyklę [2, 3]. Venkite langų, balkonų, liftų ir atvirų erdvių, o patalpos paskutiniame aukšte netinka [3].

Šaltiniai: [1] PAGD priedangų sąrašas (atvirieji duomenys, data.gov.lt) – https://get.data.gov.lt/datasets/gov/pagd/priedangos/Priedanga; [2] Priedangos – https://lt72.lt/priedangos-2-3/; [3] Oro pavojus: ką svarbu žinoti? – https://lt72.lt/rekomendacijos-oro-pavojaus-atveju/

Delsa (ms): `{"total_text": 1.6, "stt": 1069.2, "tts": 5012.5}`

## A2-power-outage-senior – Elektros sutrikimas (senjoras) ir paprastesnė formuluotė

**Sistema:** Sveiki, skambinate į civilinės saugos informacijos liniją. Jus aptarnauja dirbtinio intelekto sistema, ne žmogus. Teikiama informacija yra informacinio pobūdžio. Jei kyla pavojus gyvybei ar sveikatai, skambinkite 112. Jei norite, kad kalbėčiau lėčiau, pasakykite „lėčiau“ arba paspauskite 1. Kuo galiu padėti?

**Skambintojas:** Pas mus dingo elektra, ką daryt?

*STT atpažino:* Pas mus dingo elektra. Ka daryt?

**Sistema** (`answer`): Jei dingo elektra, pirmiausia praneškite apie pavojingą situaciją ESO nemokamu numeriu 1852 [1]. Taip pat iš kištukinių lizdų ištraukite kompiuterio ir visų kitų elektroninių buities prietaisų maitinimą [2]. Jei prognozuojama smarki liūtis ar potvyniai, išjunkite viso namo ar buto elektros įvado automatinius jungiklius [2].

Šaltiniai: [1] Kritinės situacijos (elektros tiekimo sutrikimai) – https://www.eso.lt/namams/elektra/elektros-planiniai-atjungimai-ir-sutrikimai/kritines-situacijos/4207; [2] Kritinės situacijos (elektros tiekimo sutrikimai) – https://www.eso.lt/namams/elektra/elektros-planiniai-atjungimai-ir-sutrikimai/kritines-situacijos/4207

Delsa (ms): `{"retrieval": 0.6, "llm": 808.7, "total_text": 812.5, "stt": 1216.8, "tts": 2838.2}`

**Skambintojas:** Nesupratau...

*STT atpažino:* Nesupratau

**Sistema** (`answer`): Jei dingo elektra, praneškite apie tai ESO numeriu 1852 [1]. Ištraukite kompiuterio ir kitų prietaisų laidus iš elektros lizdų [2]. Jei laukiama smarkios liūties ar potvynio, išjunkite elektros jungiklius visame name ar bute [2].

Šaltiniai: [1] Kritinės situacijos (elektros tiekimo sutrikimai) – https://www.eso.lt/namams/elektra/elektros-planiniai-atjungimai-ir-sutrikimai/kritines-situacijos/4207; [2] Kritinės situacijos (elektros tiekimo sutrikimai) – https://www.eso.lt/namams/elektra/elektros-planiniai-atjungimai-ir-sutrikimai/kritines-situacijos/4207

Delsa (ms): `{"llm": 814.8, "total_text": 815.7, "stt": 830.8, "tts": 2276.0}`

## A3-chemical-health-risk – Cheminė avarija su pavojumi sveikatai -> 112 ir operatorius

**Sistema:** Sveiki, skambinate į civilinės saugos informacijos liniją. Jus aptarnauja dirbtinio intelekto sistema, ne žmogus. Teikiama informacija yra informacinio pobūdžio. Jei kyla pavojus gyvybei ar sveikatai, skambinkite 112. Jei norite, kad kalbėčiau lėčiau, pasakykite „lėčiau“ arba paspauskite 1. Kuo galiu padėti?

**Skambintojas:** Kažkoks dūmas, sunku kvėpuoti, kaimynui bloga.

*STT atpažino:* Kažkoks dūmas, sunku kvėpuoti, kaimynui bloga

**Sistema** (`emergency_transfer`): Jei kyla pavojus gyvybei ar sveikatai, nedelsdami skambinkite 112. Dabar jus sujungsiu su operatoriumi.

Delsa (ms): `{"total_text": 1.1, "stt": 2050.1, "tts": 1057.4}`

## A4-russian-speaker – Rusakalbis skambintojas -> suderintas pranešimas ir operatorius

**Sistema:** Sveiki, skambinate į civilinės saugos informacijos liniją. Jus aptarnauja dirbtinio intelekto sistema, ne žmogus. Teikiama informacija yra informacinio pobūdžio. Jei kyla pavojus gyvybei ar sveikatai, skambinkite 112. Jei norite, kad kalbėčiau lėčiau, pasakykite „lėčiau“ arba paspauskite 1. Kuo galiu padėti?

**Skambintojas:** Здравствуйте, где ближайшее укрытие?

*STT atpažino:* Здравствуйте. Где ближайшее укрытие?

**Sistema** (`language_transfer`): Здравствуйте. Эта линия работает на литовском языке. Сейчас я соединю вас с оператором. Если есть угроза жизни или здоровью, звоните 112.

Delsa (ms): `{"total_text": 0.1, "stt": 1098.8, "tts": 1364.2}`

## A5-asks-for-human – Prašo žmogaus

**Sistema:** Sveiki, skambinate į civilinės saugos informacijos liniją. Jus aptarnauja dirbtinio intelekto sistema, ne žmogus. Teikiama informacija yra informacinio pobūdžio. Jei kyla pavojus gyvybei ar sveikatai, skambinkite 112. Jei norite, kad kalbėčiau lėčiau, pasakykite „lėčiau“ arba paspauskite 1. Kuo galiu padėti?

**Skambintojas:** Ar aš kalbu su žmogumi? Noriu su žmogumi.

*STT atpažino:* Ar aš kalbu su žmogumi, noriu su žmogumi

**Sistema** (`operator_transfer`): Ne, aš esu dirbtinio intelekto sistema. Sujungiu su operatoriumi.

Delsa (ms): `{"total_text": 1.0, "stt": 1505.9, "tts": 735.0}`

## B-active-incident – Aktyvus incidentas paminimas pasisveikinime

**Sistema:** Sveiki, skambinate į civilinės saugos informacijos liniją. Jus aptarnauja dirbtinio intelekto sistema, ne žmogus. Teikiama informacija yra informacinio pobūdžio. Jei kyla pavojus gyvybei ar sveikatai, skambinkite 112. Jei norite, kad kalbėčiau lėčiau, pasakykite „lėčiau“ arba paspauskite 1. Dėmesio, šiuo metu aktualu: Elektros tiekimo sutrikimas (Šiaulių miesto savivaldybė). Dalyje Šiaulių miesto sutrikęs elektros tiekimas. Apie gedimus praneškite ESO telefonu 1852. Jei kyla pavojus gyvybei, skambinkite 112. Kuo galiu padėti?

**Skambintojas:** Ar yra kokių nors pranešimų apie elektrą?

*STT atpažino:* Ar yra kokių nors pranešimų apie elektrą?

**Sistema** (`answer`): Šiaulių miesto savivaldybėje dalyje miesto yra sutrikęs elektros tiekimas [1]. Jei kyla pavojus gyvybei, skambinkite 112 [1]. Apie gedimus praneškite ESO telefonu 1852 [1].

Delsa (ms): `{"retrieval": 0.5, "llm": 665.9, "total_text": 668.5, "stt": 1506.9, "tts": 1817.0}`

