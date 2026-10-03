"""WhatsApp chat texts by key and language.

English and Kiswahili are written here; Kikuyu comes from reviewed translations
(apps.translations) and falls back to Kiswahili until approved. Button titles are at
most 20 characters and list-row titles at most 24 (WhatsApp limits; checked in tests).
Never names a product before an agrovet has approved a prescription.
"""

from apps.translations.catalog import register

MESSAGES = {
    # --- welcome and registration -------------------------------------------------
    "welcome": {
        "en": "Karibu {first}! 👋\n\nI'm the *AgriSense Hub* assistant for tomato farmers.\n"
        "📸 Upload a photo of a sick tomato to check for *late or early blight*\n"
        "✅ Get the diagnosis confirmed by a verified agrovet\n"
        "🏪 Buy genuine, PCPB-registered treatment and pay with M-Pesa\n\n"
        "Registering only needs your phone number.",
        "sw": "Karibu {first}! 👋\n\nMimi ni msaidizi wa *AgriSense Hub* kwa wakulima wa nyanya.\n"
        "📸 Tuma picha ya nyanya mgonjwa kuchunguza *baa chelewa au baa mapema*\n"
        "✅ Pata utambuzi uliothibitishwa na agrovet aliyeidhinishwa\n"
        "🏪 Nunua dawa halisi zilizosajiliwa na PCPB na ulipe kwa M-Pesa\n\n"
        "Kujisajili kunahitaji nambari yako ya simu pekee.",
    },
    "btn_register": {"en": "Register", "sw": "Jisajili"},
    "btn_how": {"en": "How it works", "sw": "Inavyofanya kazi"},
    "how_it_works": {
        "en": "*How AgriSense works* 🌱\n\n1️⃣ Upload 3 photos of the sick tomato and answer 4 quick "
        "questions\n"
        "2️⃣ The computer checks for late or early blight\n3️⃣ A verified agrovet near you confirms it\n"
        "4️⃣ The agrovet prescribes a PCPB-registered product\n"
        "5️⃣ Buy it from a verified store with M-Pesa, then photograph the label so we can check it is "
        "genuine",
        "sw": "*AgriSense inavyofanya kazi* 🌱\n\n1️⃣ Tuma picha 3 za nyanya mgonjwa na ujibu maswali 4 "
        "mafupi\n"
        "2️⃣ Kompyuta inachunguza baa chelewa au baa mapema\n3️⃣ Agrovet aliyeidhinishwa karibu nawe "
        "anathibitisha\n"
        "4️⃣ Agrovet anaandika dawa iliyosajiliwa na PCPB\n"
        "5️⃣ Inunue dukani lililoidhinishwa kwa M-Pesa, kisha upige picha ya lebo tuthibitishe ni halisi",
    },
    "consent": {
        "en": "📱 You will register with *{phone}*.\n\n"
        "🔒 By agreeing, you allow AgriSense to store your phone number, farm location and crop photos "
        "to diagnose your tomatoes and improve advice for farmers near you (Data Protection Act, 2019).",
        "sw": "📱 Utasajiliwa kwa nambari *{phone}*.\n\n"
        "🔒 Kwa kukubali, unaruhusu AgriSense ihifadhi nambari yako ya simu, mahali shamba lilipo na "
        "picha za mimea ili kutambua magonjwa ya nyanya na kuboresha ushauri kwa wakulima walio karibu "
        "nawe (Sheria ya Ulinzi wa Data, 2019).",
    },
    "btn_agree": {"en": "I agree ✅", "sw": "Nakubali ✅"},
    "btn_decline": {"en": "No thanks", "sw": "Hapana asante"},
    "declined": {
        "en": "No problem, nothing has been saved. Send HI whenever you are ready.",
        "sw": "Sawa, hakuna kilichohifadhiwa. Tuma HI ukiwa tayari.",
    },
    "registered": {"en": "🎉 You're registered, {first}!", "sw": "🎉 Umesajiliwa, {first}!"},
    "ask_language": {"en": "Which language do you prefer?", "sw": "Unapendelea lugha gani?"},
    # --- farm location: region -> county -> sub-county -> ward ---------------------------
    "loc_region": {
        "en": "📍 *Where is your farm?*\n\nChoose your *region*.",
        "sw": "📍 *Shamba lako liko wapi?*\n\nChagua *eneo* lako.",
    },
    "btn_region": {"en": "Choose region", "sw": "Chagua eneo"},
    "loc_county": {
        "en": "📍 *Where is your farm?*\n\n{region} region: choose your *county*.",
        "sw": "📍 *Shamba lako liko wapi?*\n\nEneo la {region}: chagua *kaunti* yako.",
    },
    "loc_sub_county": {
        "en": "📍 {county} county: choose your *sub-county*.",
        "sw": "📍 Kaunti ya {county}: chagua *kaunti ndogo* yako.",
    },
    "loc_ward": {
        "en": "📍 {sub_county}, {county}: choose your *ward*.",
        "sw": "📍 {sub_county}, {county}: chagua *wadi* yako.",
    },
    "btn_county": {"en": "Choose county", "sw": "Chagua kaunti"},
    "btn_sub_county": {"en": "Choose sub-county", "sw": "Chagua kaunti ndogo"},
    "btn_ward": {"en": "Choose ward", "sw": "Chagua wadi"},
    "row_more": {"en": "More ➡️", "sw": "Zaidi ➡️"},
    "loc_saved": {
        "en": "✅ Farm location saved: {ward}, {sub_county}, {county}.",
        "sw": "✅ Mahali pa shamba pamehifadhiwa: {ward}, {sub_county}, {county}.",
    },
    "linked": {
        "en": "👋 Welcome back, {first}! This WhatsApp number is linked to your AgriSense account.",
        "sw": "👋 Karibu tena, {first}! Nambari hii ya WhatsApp imeunganishwa na akaunti yako ya AgriSense.",
    },
    # --- menu -------------------------------------------------------------------
    "menu_body": {
        "en": "Hi {first}, what would you like to do?",
        "sw": "Habari {first}, ungependa kufanya nini?",
    },
    "menu_button": {"en": "Open menu", "sw": "Fungua menyu"},
    "row_report": {"en": "📸 Upload tomato photo", "sw": "📸 Tuma picha ya nyanya"},
    "row_report_d": {"en": "Check for late or early blight", "sw": "Chunguza baa chelewa au mapema"},
    "row_cases": {"en": "📋 My reports", "sw": "📋 Ripoti zangu"},
    "row_cases_d": {"en": "Diagnoses and prescriptions", "sw": "Utambuzi na maagizo ya dawa"},
    "row_orders": {"en": "🧾 My orders", "sw": "🧾 Oda zangu"},
    "row_orders_d": {"en": "Payments, pickup, label checks", "sw": "Malipo, kuchukua, lebo"},
    "row_rewards": {"en": "🎁 My points", "sw": "🎁 Pointi zangu"},
    "row_rewards_d": {"en": "Rewards for verified purchases", "sw": "Zawadi za ununuzi uliothibitishwa"},
    "row_location": {"en": "📍 My farm location", "sw": "📍 Mahali pa shamba"},
    "row_location_d": {"en": "County, sub-county, ward", "sw": "Kaunti, kaunti ndogo, wadi"},
    "row_language": {"en": "🗣️ Language", "sw": "🗣️ Lugha"},
    "row_language_d": {"en": "English, Kiswahili, Gĩkũyũ", "sw": "Kiingereza, Kiswahili, Gĩkũyũ"},
    "row_help": {"en": "❓ Help", "sw": "❓ Msaada"},
    "row_help_d": {"en": "How to use AgriSense", "sw": "Jinsi ya kutumia AgriSense"},
    "btn_menu": {"en": "Main menu", "sw": "Menyu kuu"},
    "language_set": {"en": "✅ Language updated.", "sw": "✅ Lugha imebadilishwa."},
    "help": {
        "en": "❓ *Help*\n\n• Type *MENU* anytime for the main menu\n• Type *CANCEL* to stop what you are "
        "doing\n"
        "• Payments are by M-Pesa: you only enter your PIN on your phone's M-Pesa prompt\n\n"
        "AgriSense never asks for your M-Pesa PIN in this chat.",
        "sw": "❓ *Msaada*\n\n• Andika *MENU* wakati wowote kwa menyu kuu\n• Andika *CANCEL* kusimamisha "
        "unachofanya\n"
        "• Malipo ni kwa M-Pesa: unaweka PIN tu kwenye ujumbe wa M-Pesa kwenye simu yako\n\n"
        "AgriSense haitawahi kukuuliza PIN yako ya M-Pesa kwenye mazungumzo haya.",
    },
    "didnt_understand": {
        "en": "Sorry, I didn't get that. Please use the buttons, or type MENU.",
        "sw": "Samahani, sijaelewa. Tafadhali tumia vitufe, au andika MENU.",
    },
    "error": {
        "en": "😕 Something went wrong on our side. Please try again in a moment.",
        "sw": "😕 Kuna hitilafu upande wetu. Tafadhali jaribu tena baada ya muda mfupi.",
    },
    # --- report a problem (Detect) ---------------------------------------------------
    "ask_location": {
        "en": "📍 Optional: share your exact farm pin so we can show the nearest agrovets and how far "
        "they are. Tap the button below, or type SKIP.",
        "sw": "📍 Si lazima: tuma alama ya mahali shamba lilipo ili tukuonyeshe agrovet walio karibu "
        "zaidi na umbali wao. Gusa kitufe hapa chini, au andika SKIP.",
    },
    "photo_leaf": {
        "en": "📸 *Photo 1 of 3:* a close-up of a *sick leaf*. Get close so the spots fill the photo, in "
        "daylight.",
        "sw": "📸 *Picha 1 kati ya 3:* jani *lililo mgonjwa* kwa karibu. Sogea karibu ili madoa yajaze "
        "picha, "
        "kwenye mwanga wa mchana.",
    },
    "photo_plant": {
        "en": "📸 *Photo 2 of 3:* the *whole plant*, standing back so all of it is in the photo.",
        "sw": "📸 *Picha 2 kati ya 3:* *mmea mzima*, simama mbali kidogo ili wote uonekane kwenye picha.",
    },
    "photo_stem_fruit": {
        "en": "📸 *Photo 3 of 3:* the *stem or fruit*, wherever you see damage.",
        "sw": "📸 *Picha 3 kati ya 3:* *shina au tunda*, popote unapoona madhara.",
    },
    "need_photo": {
        "en": "Please send a *photo* 📸 (tap the 📎 or camera icon).",
        "sw": "Tafadhali tuma *picha* 📸 (gusa alama ya 📎 au kamera).",
    },
    "q_started": {
        "en": "❓ *When did you first notice the problem?*",
        "sw": "❓ *Uliona tatizo kwa mara ya kwanza lini?*",
    },
    "btn_choose": {"en": "Choose", "sw": "Chagua"},
    "started_less_than_3_days": {"en": "Less than 3 days ago", "sw": "Chini ya siku 3"},
    "started_3_to_7_days": {"en": "3 to 7 days ago", "sw": "Siku 3 hadi 7"},
    "started_1_to_2_weeks": {"en": "1 to 2 weeks ago", "sw": "Wiki 1 hadi 2"},
    "started_over_2_weeks": {"en": "Over 2 weeks ago", "sw": "Zaidi ya wiki 2"},
    "q_share": {
        "en": "❓ *How many of your tomato plants are affected?*",
        "sw": "❓ *Mimea mingapi ya nyanya imeathirika?*",
    },
    "share_few": {"en": "A few (<10%)", "sw": "Michache (<10%)"},
    "share_some": {"en": "Some (10-50%)", "sw": "Baadhi (10-50%)"},
    "share_most": {"en": "Most (>50%)", "sw": "Mingi (>50%)"},
    "q_weather": {
        "en": "❓ *What has the weather been like this past week?*",
        "sw": "❓ *Hali ya hewa imekuwaje wiki hii iliyopita?*",
    },
    "weather_rainy": {"en": "Rainy", "sw": "Mvua"},
    "weather_humid": {"en": "Humid / misty", "sw": "Unyevu / ukungu"},
    "weather_hot_dry": {"en": "Hot and dry", "sw": "Joto na ukame"},
    "weather_cold": {"en": "Cold", "sw": "Baridi"},
    "weather_normal": {"en": "Normal", "sw": "Kawaida"},
    "q_sprayed": {
        "en": "❓ *Have you already sprayed anything on these plants?*",
        "sw": "❓ *Je, tayari umenyunyizia chochote kwenye mimea hii?*",
    },
    "btn_yes": {"en": "Yes", "sw": "Ndiyo"},
    "btn_no": {"en": "No", "sw": "Hapana"},
    "ask_sprayed_product": {
        "en": "What did you spray? Type the product name (or SKIP if you don't know).",
        "sw": "Ulinyunyizia nini? Andika jina la dawa (au SKIP kama hujui).",
    },
    "submitted": {
        "en": "✅ *Report sent!*\n\nThe computer is checking your photos now, then a verified agrovet "
        "near "
        "you "
        "will confirm. I'll message you here at each step. 🙏",
        "sw": "✅ *Ripoti imetumwa!*\n\nKompyuta inakagua picha zako sasa, kisha agrovet aliyeidhinishwa "
        "karibu "
        "nawe atathibitisha. Nitakutumia ujumbe hapa kila hatua. 🙏",
    },
    "report_in_progress": {
        "en": "You already have a report in progress. Please finish it, or type CANCEL to start again.",
        "sw": "Tayari una ripoti inayoendelea. Tafadhali imalize, au andika CANCEL kuanza upya.",
    },
    "btn_retake": {"en": "Send new photos", "sw": "Tuma picha mpya"},
    # --- reports list ---------------------------------------------------------------
    "cases_empty": {
        "en": "You have no reports yet. Choose *Report a problem* to start.",
        "sw": "Bado huna ripoti. Chagua *Ripoti tatizo* kuanza.",
    },
    "cases_title": {"en": "📋 *Your recent reports*", "sw": "📋 *Ripoti zako za hivi karibuni*"},
    # --- buying (Module 4) ---------------------------------------------------------------
    "btn_find_stores": {"en": "Find stores", "sw": "Tafuta maduka"},
    "stores_body": {
        "en": "🏪 Verified stores with your prescribed product ({code}), nearest first. All are "
        "PCPB-registered.",
        "sw": "🏪 Maduka yaliyoidhinishwa yenye dawa uliyoandikiwa ({code}), yaliyo karibu kwanza. "
        "Zote zimesajiliwa na PCPB.",
    },
    "stores_button": {"en": "See stores", "sw": "Ona maduka"},
    "no_stores": {
        "en": "No verified store near you has this product in stock right now. Please try again later or "
        "ask your agrovet.",
        "sw": "Hakuna duka lililoidhinishwa karibu nawe lenye dawa hii sasa hivi. Tafadhali jaribu "
        "baadaye "
        "au "
        "muulize agrovet wako.",
    },
    "store_detail": {
        "en": "*{product}*\n🛡️ PCPB No: {pcpb}\n🏪 {agrovet}{distance}\n💰 *KES {price}*\n\nHow would you "
        "like to pay?",
        "sw": "*{product}*\n🛡️ Nambari ya PCPB: {pcpb}\n🏪 {agrovet}{distance}\n💰 *KES {price}*\n\n"
        "Ungependa kulipa vipi?",
    },
    "btn_pay_mpesa": {"en": "Pay with M-Pesa", "sw": "Lipa kwa M-Pesa"},
    "btn_pay_shop": {"en": "Pay at the shop", "sw": "Lipa dukani"},
    "stk_sent": {
        "en": "📲 Check your phone and enter your M-Pesa PIN to pay *KES {amount}*. I'll confirm here "
        "when "
        "the payment is received.",
        "sw": "📲 Angalia simu yako na uweke PIN ya M-Pesa kulipa *KES {amount}*. Nitathibitisha hapa "
        "malipo "
        "yakipokelewa.",
    },
    "reserved": {
        "en": "✅ *Reserved at {agrovet}.*\n\nShow your prescription code *{code}* at the counter and pay "
        "there.\n\n"
        "📷 After you collect it, I'll ask you to photograph the label so we can check it is genuine.",
        "sw": "✅ *Imehifadhiwa kwa {agrovet}.*\n\nOnyesha nambari ya agizo *{code}* dukani na ulipe "
        "hapo.\n\n"
        "📷 Ukiichukua, nitakuomba upige picha ya lebo tuthibitishe ni halisi.",
    },
    "paid": {
        "en": "✅ *Payment received!* M-Pesa receipt {receipt}.\n\nCollect your {product} at *{agrovet}* "
        "and show "
        "the code *{code}* at the counter.\n\n📷 After you collect it, I'll ask you to photograph the "
        "label.",
        "sw": "✅ *Malipo yamepokelewa!* Risiti ya M-Pesa {receipt}.\n\nChukua {product} kwa "
        "*{agrovet}* na "
        "uonyeshe nambari *{code}* dukani.\n\n📷 Ukiichukua, nitakuomba upige picha ya lebo.",
    },
    "payment_failed": {
        "en": "❌ The M-Pesa payment did not go through ({reason}). You can try again.",
        "sw": "❌ Malipo ya M-Pesa hayakufanikiwa ({reason}). Unaweza kujaribu tena.",
    },
    "btn_try_again": {"en": "Try again", "sw": "Jaribu tena"},
    "label_prompt": {
        "en": "📦 *{agrovet}* has handed over your {product}.\n\n📷 Now send a clear photo of the product "
        "*label* "
        "showing the PCPB number, so we can check it is genuine.",
        "sw": "📦 *{agrovet}* amekukabidhi {product}.\n\n📷 Sasa tuma picha iliyo wazi ya *lebo* ya dawa "
        "inayoonyesha nambari ya PCPB, tuthibitishe ni halisi.",
    },
    "label_checking": {
        "en": "🔎 Checking the label against the PCPB register…",
        "sw": "🔎 Ninalinganisha lebo na rejista ya PCPB…",
    },
    "label_verified": {
        "en": "✅ *Verified genuine!*\n\n{product}\nRegistered and exactly what was prescribed. Follow "
        "the "
        "label "
        "and wear gloves when spraying.\n\n🎁 +{points} points. Your balance: {balance}.",
        "sw": "✅ *Imethibitishwa ni halisi!*\n\n{product}\nImesajiliwa na ndiyo uliyoandikiwa. Fuata "
        "lebo na "
        "vaa glavu unaponyunyizia.\n\n🎁 Pointi +{points}. Salio lako: {balance}.",
    },
    "label_not_registered": {
        "en": "⚠️ *Not a registered product. Do not use it.*\n\nKeep the product and receipt. We have "
        "flagged the "
        "store. Choose *Find stores* again to buy from another verified store.",
        "sw": "⚠️ *Dawa hii haijasajiliwa. Usiitumie.*\n\nHifadhi dawa na risiti. Tumeripoti duka hilo. "
        "Chagua "
        "*Tafuta maduka* tena kununua kutoka duka lingine lililoidhinishwa.",
    },
    "label_not_prescribed": {
        "en": "⚠️ *Registered, but not what was prescribed for this disease.*\n\nPlease return it to the "
        "store "
        "and ask for the prescribed product.",
        "sw": "⚠️ *Imesajiliwa, lakini si uliyoandikiwa kwa ugonjwa huu.*\n\nTafadhali irudishe dukani "
        "na "
        "uombe "
        "dawa uliyoandikiwa.",
    },
    "label_unreadable": {
        "en": "🤔 I couldn't read a PCPB number. Please send a closer, brighter photo of the label.",
        "sw": "🤔 Sikuweza kusoma nambari ya PCPB. Tafadhali tuma picha ya karibu zaidi na yenye mwanga "
        "ya "
        "lebo.",
    },
    "orders_empty": {"en": "You have no orders yet.", "sw": "Bado huna oda."},
    "orders_title": {"en": "🧾 *Your recent orders*", "sw": "🧾 *Oda zako za hivi karibuni*"},
    "rewards": {
        "en": "🎁 You have *{balance} points*. Earn 10 points for every verified purchase.",
        "sw": "🎁 Una *pointi {balance}*. Pata pointi 10 kwa kila ununuzi uliothibitishwa.",
    },
}

_catalog = register("whatsapp", MESSAGES)


def text(key: str, language: str = "en", **values) -> str:
    return _catalog.text(key, language, **values)
