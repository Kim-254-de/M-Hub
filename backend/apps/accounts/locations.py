"""Service areas: region -> county -> sub-county -> ward.

Sub-counties are the IEBC constituencies, so every ward belongs to exactly one of them.
Ward lists follow IEBC (2012 boundaries), via the kenya-locations dataset.
"""

REGIONS: dict[str, dict[str, dict[str, list[str]]]] = {
    "Mt. Kenya": {
        "Meru": {
            "Buuri": ["Kibirichia", "Kiirua/Naari", "Kisima", "Ruiri/Rwarera", "Timau"],
            "Central Imenti": ["Abothuguchi Central", "Abothuguchi West", "Kiagu", "Mwanganthia"],
            "Igembe Central": ["Akirang'ondu", "Athiru ruujine", "Igembe East", "Kangeta", "Njia"],
            "Igembe North": ["Amwathi", "Antuambui", "Antubetwe kiongo", "Naathu", "Ntunene"],
            "Igembe South": ["Akachiu", "Athiru gaiti", "Kanuni", "Kiegoi/Antubochiu", "Maua"],
            "North Imenti": ["Municipality", "Ntima East", "Ntima West", "Nyaki East", "Nyaki West"],
            "South Imenti": [
                "Abogeta East",
                "Abogeta West",
                "Igoji East",
                "Igoji West",
                "Mitunguu",
                "Nkuene",
            ],
            "Tigania East": ["Karama", "Kiguchwa", "Mikinduri", "Muthara", "Thangatha"],
            "Tigania West": ["Akithii", "Athwana", "Kianjai", "Mbeu", "Nkomo"],
        },
        "Tharaka-Nithi": {
            "Chuka/Igambang'ombe": ["Igambang'ombe", "Karingani", "Magumoni", "Mariani", "Mugwe"],
            "Maara": ["Chogoria", "Ganga", "Mitheru", "Muthambi", "Mwimbi"],
            "Tharaka": ["Chiakariga", "Gatunga", "Marimanti", "Mukothima", "Nkondi"],
        },
        "Embu": {
            "Manyatta": ["Gaturi South", "Kirimari", "Kithimu", "Mbeti North", "Nginda", "Ruguru/Ngandori"],
            "Mbeere North": ["Evurore", "Muminji", "Nthawa"],
            "Mbeere South": ["Kiambere", "Makima", "Mavuria", "Mbeti South", "Mwea"],
            "Runyenjes": [
                "Central  ward",
                "Gaturi North",
                "Kagaari North",
                "Kagaari South",
                "Kyeni North",
                "Kyeni South",
            ],
        },
        "Kirinyaga": {
            "Gichugu": ["Baragwi", "Kabare", "Karumandi", "Ngariama", "Njukiini"],
            "Kirinyaga Central": ["Inoi", "Kanyeki-ini", "Kerugoya", "Mutira"],
            "Mwea": [
                "Gathigiriri",
                "Kangai",
                "Murinduko",
                "Mutithi",
                "Nyangati",
                "Tebere",
                "Thiba",
                "Wamumu",
            ],
            "Ndia": ["Kariti", "Kiine", "Mukure"],
        },
        "Murang'a": {
            "Gatanga": ["Gatanga", "Ithanga", "Kakuzi/Mitubiri", "Kariara", "Kihumbu-ini", "Mugumo-ini"],
            "Kandara": ["Gaichanjiru", "Ithiru", "Kagundu-ini", "Muruka", "Ng'araria", "Ruchu"],
            "Kangema": ["Kanyenyaini", "Muguru", "Rwathia"],
            "Kigumo": ["Kahumbu", "Kangari", "Kigumo", "Kinyona", "Muthithi"],
            "Kiharu": ["Gaturi", "Mbiri", "Mugoiri", "Murarandia", "Township", "Wangu"],
            "Maragwa": ["Ichagaki", "Kamahuha", "Kambiti", "Kimorori/Wempa", "Makuyu", "Nginda"],
            "Mathioya": ["Gitugi", "Kamacharia", "Kiru"],
        },
        "Nyeri": {
            "Kieni": [
                "Gakawa",
                "Gatarakwa",
                "Kabaru",
                "Mugunda",
                "Mweiga",
                "Mwiyogo/Endarasha",
                "Naromoru kiamathaga",
                "Thegu River",
            ],
            "Mathira": ["Iriaini", "Karatina Town", "Kirimukuyu", "Konyu", "Magutu", "Ruguru"],
            "Mukurweini": ["Gikondi", "Mukurwe-ini Central", "Mukurwe-ini West", "Rugi"],
            "Nyeri Town": ["Gatitu/Muruguru", "Kamakwa/Mukaro", "Kiganjo/Mathari", "Ruring'u", "Rware"],
            "Othaya": ["Chinga", "Iria-ini", "Karima", "Mahiga"],
            "Tetu": ["Aguthi/Gaaki", "Dedan kimanthi", "Wamagana"],
        },
        "Kiambu": {
            "Gatundu North": ["Chania", "Githobokoni", "Gituamba", "Mang'u"],
            "Gatundu South": ["Kiamwangi", "Kiganjo", "Ndarugu", "Ngenda"],
            "Githunguri": ["Githiga", "Githunguri", "Ikinu", "Komothai", "Ngewa"],
            "Juja": ["Juja", "Kalimoni", "Murera", "Theta", "Witeithie"],
            "Kabete": ["Gitaru", "Kabete", "Muguga", "Nyadhuna", "Uthiru"],
            "Kiambaa": ["Cianda", "Karuri", "Kihara", "Muchatha", "Ndenderu"],
            "Kiambu": ["Ndumberi", "Riabai", "Ting'ang'a", "Township"],
            "Kikuyu": ["Karai", "Kikuyu", "Kinoo", "Nachu", "Sigona"],
            "Lari": ["Kamburu", "Kijabe", "Kinale", "Lari/Kirenga", "Nyanduma"],
            "Limuru": ["Bibirioni", "Limuru Central", "Limuru East", "Ndeiya", "Ngecha tigoni"],
            "Ruiru": [
                "Biashara",
                "Gatongora",
                "Gitothua",
                "Kahawa sukari",
                "Kahawa wendani",
                "Kiuu",
                "Mwihoko",
                "Mwiki",
            ],
            "Thika Town": ["Gatuanyaga", "Hospital", "Kamenu", "Ngoliba", "Township"],
        },
        "Nyandarua": {
            "Kinangop": [
                "Engineer",
                "Gathara",
                "Githabai",
                "Magumu",
                "Murungaru",
                "Njabini/kiburu",
                "North kinangop",
                "Nyakio",
            ],
            "Kipipiri": ["Geta", "Githioro", "Kipipiri", "Wanjohi"],
            "Ndaragwa": ["Central", "Kiriita", "Leshau pondo", "Shamata"],
            "Ol Jorok": ["Charagita", "Gathanji", "Gatimu", "Weru"],
            "Ol Kalou": ["Kaimbaga", "Kanjuiri ridge", "Karau", "Mirangine", "Rurii"],
        },
        "Laikipia": {
            "Laikipia East": ["Nanyuki", "Ngobit", "Thingithu", "Tigithi", "Umande"],
            "Laikipia North": ["Mukogondo East", "Mukogondo West", "Segera", "Sosian"],
            "Laikipia West": ["Igwamiti", "Kinamba", "Marmanet", "Olmoran", "Rumuruti Township", "Salama"],
        },
    },
}


def counties(region: str) -> list[str]:
    return list(REGIONS.get(region, {}))


def sub_counties(region: str, county: str) -> list[str]:
    return list(REGIONS.get(region, {}).get(county, {}))


def wards(region: str, county: str, sub_county: str) -> list[str]:
    return list(REGIONS.get(region, {}).get(county, {}).get(sub_county, []))
