"""Generic catalog of makes and models for the seed (real brand/model names are fine —
this is a public catalog, not company data). Format: make -> [(model, type or None)].
"""

CAR, VAN, MOTO, CAMPER, TRUCK = "car", "van", "motorcycle", "camper", "truck"

CATALOG: dict[str, list[tuple[str, str | None]]] = {
    "Audi": [
        (m, CAR)
        for m in (
            "A1",
            "A3",
            "A4",
            "A5",
            "A6",
            "A8",
            "Q2",
            "Q3",
            "Q5",
            "Q7",
            "Q8",
            "e-tron GT",
            "TT",
        )
    ],
    "BMW": [
        (m, CAR)
        for m in (
            "Serija 1",
            "Serija 2",
            "Serija 3",
            "Serija 4",
            "Serija 5",
            "Serija 7",
            "X1",
            "X3",
            "X5",
            "X6",
            "i4",
            "iX",
        )
    ]
    + [(m, MOTO) for m in ("R 1250 GS", "F 900 R", "S 1000 RR")],
    "Citroën": [(m, CAR) for m in ("C3", "C3 Aircross", "C4", "C5 Aircross", "Berlingo")]
    + [(m, VAN) for m in ("Jumpy", "Jumper")],
    "Dacia": [(m, CAR) for m in ("Sandero", "Logan", "Duster", "Jogger", "Spring")],
    "Fiat": [(m, CAR) for m in ("500", "Panda", "Tipo", "500X")]
    + [(m, VAN) for m in ("Doblo", "Ducato", "Scudo")]
    + [("Ducato kamper", CAMPER)],
    "Ford": [(m, CAR) for m in ("Fiesta", "Focus", "Puma", "Kuga", "Mondeo", "Mustang", "Ranger")]
    + [(m, VAN) for m in ("Transit", "Transit Custom", "Transit Connect", "Tourneo Custom")],
    "Honda": [(m, CAR) for m in ("Jazz", "Civic", "HR-V", "CR-V")]
    + [(m, MOTO) for m in ("CB500F", "Africa Twin", "PCX 125", "NC750X")],
    "Hyundai": [(m, CAR) for m in ("i10", "i20", "i30", "Kona", "Tucson", "Santa Fe", "Ioniq 5")],
    "Kia": [
        (m, CAR) for m in ("Picanto", "Rio", "Ceed", "Stonic", "Sportage", "Sorento", "EV6", "Niro")
    ],
    "Mercedes-Benz": [
        (m, CAR)
        for m in ("A-klasa", "B-klasa", "C-klasa", "E-klasa", "S-klasa", "GLA", "GLC", "GLE", "EQA")
    ]
    + [(m, VAN) for m in ("Vito", "Sprinter", "Citan")]
    + [("Actros", TRUCK), ("Atego", TRUCK)],
    "Nissan": [(m, CAR) for m in ("Micra", "Juke", "Qashqai", "X-Trail", "Leaf")]
    + [(m, VAN) for m in ("Primastar", "Interstar")],
    "Opel": [(m, CAR) for m in ("Corsa", "Astra", "Mokka", "Grandland", "Insignia")]
    + [(m, VAN) for m in ("Vivaro", "Movano", "Combo")],
    "Peugeot": [(m, CAR) for m in ("208", "308", "508", "2008", "3008", "5008")]
    + [(m, VAN) for m in ("Partner", "Expert", "Boxer")],
    "Renault": [(m, CAR) for m in ("Clio", "Captur", "Megane", "Austral", "Arkana", "Zoe")]
    + [(m, VAN) for m in ("Kangoo", "Trafic", "Master")],
    "Seat": [(m, CAR) for m in ("Ibiza", "Leon", "Arona", "Ateca", "Tarraco")],
    "Škoda": [
        (m, CAR)
        for m in ("Fabia", "Scala", "Octavia", "Superb", "Kamiq", "Karoq", "Kodiaq", "Enyaq")
    ],
    "Suzuki": [(m, CAR) for m in ("Swift", "Ignis", "Vitara", "S-Cross", "Jimny")]
    + [(m, MOTO) for m in ("V-Strom 650", "GSX-S750", "Burgman 400")],
    "Tesla": [(m, CAR) for m in ("Model 3", "Model Y", "Model S", "Model X")],
    "Toyota": [
        (m, CAR)
        for m in (
            "Aygo X",
            "Yaris",
            "Yaris Cross",
            "Corolla",
            "C-HR",
            "RAV4",
            "Land Cruiser",
            "Hilux",
        )
    ]
    + [(m, VAN) for m in ("Proace", "Proace City")],
    "Volkswagen": [
        (m, CAR)
        for m in (
            "Polo",
            "Golf",
            "Passat",
            "Arteon",
            "T-Roc",
            "Tiguan",
            "Touareg",
            "ID.3",
            "ID.4",
            "Touran",
        )
    ]
    + [(m, VAN) for m in ("Caddy", "Transporter", "Crafter", "Multivan")]
    + [("California", CAMPER), ("Grand California", CAMPER)],
    "Volvo": [(m, CAR) for m in ("XC40", "XC60", "XC90", "V60", "V90", "S60", "EX30")]
    + [(m, TRUCK) for m in ("FH", "FM")],
    "Iveco": [
        ("Daily", VAN),
        ("Eurocargo", TRUCK),
        ("S-Way", TRUCK),
        ("Stralis", TRUCK),
        ("Trakker", TRUCK),
    ],
    "MAN": [("TGE", VAN), ("TGL", TRUCK), ("TGM", TRUCK), ("TGS", TRUCK), ("TGX", TRUCK)],
    "Scania": [(m, TRUCK) for m in ("R 450", "R 500", "S 500", "G 410", "P 280")],
    "Yamaha": [
        (m, MOTO)
        for m in ("MT-07", "MT-09", "Tracer 9", "Ténéré 700", "XMAX 300", "YZF-R7", "NMAX 125")
    ],
    "Kawasaki": [(m, MOTO) for m in ("Z650", "Z900", "Ninja 650", "Versys 650", "Vulcan S")],
    "KTM": [
        (m, MOTO)
        for m in (
            "125 Duke",
            "390 Duke",
            "790 Duke",
            "890 Adventure",
            "1290 Super Adventure",
            "EXC 300",
        )
    ],
    "Piaggio": [
        (m, MOTO)
        for m in ("Vespa Primavera", "Vespa GTS 300", "Beverly 400", "Liberty 125", "MP3 530")
    ],
    "Adria": [(m, CAMPER) for m in ("Coral", "Matrix", "Sonic", "Twin", "Adora", "Altea")],
    "Knaus": [(m, CAMPER) for m in ("Sky TI", "Van TI", "BoxStar", "Sport", "Südwind")],
    "Hymer": [(m, CAMPER) for m in ("B-Klasse", "Exsis", "ML-T", "Free", "Eriba Touring")],
}
