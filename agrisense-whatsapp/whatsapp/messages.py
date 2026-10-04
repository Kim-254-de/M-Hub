"""All farmer-facing text in one place, so it can be translated.

`t(key, lang, **kw)` looks the key up in the farmer's language and falls back
to English. English is the default; Kiswahili is offered at registration.
Have a native speaker review SW before real farmers use it.
"""

EN = {
    # --- welcome & registration -------------------------------------------
    "welcome": (
        "Karibu {name}! 👋\n\n"
        "I'm the *AgriSense Hub* assistant for tomato farmers. I help you:\n"
        "🔍 Check your tomato for diseases from a photo\n"
        "✅ Get the diagnosis *confirmed by a verified agrovet*\n"
        "🏪 Buy *genuine, PCPB-registered* treatment near you — and pay with M-Pesa\n\n"
        "To get started, let's register you. It takes about 1 minute."
    ),
    "btn_register": "Register",
    "btn_how": "How it works",
    "how_it_works": (
        "*How AgriSense works* 🌱\n\n"
        "1️⃣ Send a photo of the sick tomato leaf or fruit\n"
        "2️⃣ Our AI suggests what the problem is\n"
        "3️⃣ A *verified agrovet* near you checks the photo and confirms it\n"
        "4️⃣ Buy a *PCPB-registered* product from a verified agrovet with M-Pesa\n"
        "5️⃣ Photograph the label when you collect it — we check it's genuine and you earn points"
    ),
    "ask_name": "What is your *full name*?",
    "bad_name": "Please type your full name (at least 2 letters).",
    "ask_county": "Thanks, {first}! Which *county* is your farm in?",
    "btn_choose_county": "Choose county",
    "ask_county_text": "Please type the name of your county.",
    "ask_ward": "Which *ward or village* is the farm in?",
    "ask_language": "Which language do you prefer?",
    "confirm_reg": (
        "Please confirm your details:\n\n"
        "👤 Name: {name}\n📍 County: {county}\n🏘️ Ward/Village: {ward}\n"
        "🍅 Crop: Tomato\n🗣️ Language: {language}\n\n"
        "🔒 By confirming, you agree that AgriSense stores these details and your crop photos "
        "to diagnose your crops and improve advice for farmers near you."
    ),
    "btn_confirm": "Confirm ✅",
    "btn_edit": "Edit details",
    "registered": "🎉 You're registered, {first}! Welcome to AgriSense Hub.",
    # --- main menu ----------------------------------------------------------
    "menu_body": "Hi {first}, what would you like to do today?",
    "menu_button": "Open menu",
    "menu_footer": "Type MENU anytime to come back here",
    "sec_crop": "Crop health",
    "sec_shop": "Buy & find",
    "sec_account": "Account",
    "row_diag": "🔍 Check my tomato",
    "row_diag_d": "Send a photo, get a confirmed diagnosis",
    "row_hist": "📋 My history",
    "row_hist_d": "Past diagnoses and orders",
    "row_agrovets": "🏪 Agrovets near me",
    "row_agrovets_d": "Verified shops in {county}",
    "row_profile": "👤 My profile",
    "row_profile_d": "Your details, points and language",
    "row_help": "❓ Help",
    "row_help_d": "How to use AgriSense",
    "btn_menu": "Main menu",
    # --- diagnosis -----------------------------------------------------------
    "ask_photo": (
        "📸 Send *one clear photo* of the sick tomato leaf or fruit.\n\n"
        "Tips:\n• Take it in daylight\n• Get close so the spots fill the photo\n• Keep the camera steady"
    ),
    "need_photo": "Please send a *photo* 📸 — tap the 📎 or camera icon.",
    "checking": "⏳ Checking your tomato photo… this takes a few seconds.",
    "diag_failed": "😕 Sorry, I couldn't check the photo right now. Please try again in a moment.",
    "not_clear": (
        "🤔 I couldn't see a tomato plant clearly in that photo. "
        "Please send a closer, brighter photo of the sick leaf."
    ),
    "diag_ai_pending": (
        "🤖 *AI suggestion:* {disease} ({pct}% sure)\n\n"
        "A *verified agrovet* near you is now checking your photo to confirm. "
        "You'll get the confirmed diagnosis and what to buy right here. 🙏"
    ),
    "diag_prevention": "🛡️ *While you wait — do this now:*\n{prevention}",
    "btn_try_again": "Try again",
    "no_agrovet": "There's no verified agrovet registered in {county} yet. We'll notify you as soon as one is available.",
    "agrovet_confirmed": (
        "✅ *Confirmed by {agrovet}*\n\nYour tomato has *{disease}*.{note}\n\n"
        "Tap *Buy treatment* to see genuine, PCPB-registered products from verified agrovets."
    ),
    "agrovet_corrected": (
        "📝 *Checked by {agrovet}*\n\nThe AI was not right. Your tomato has *{disease}*.{note}\n\n"
        "Tap *Buy treatment* to see genuine, PCPB-registered products from verified agrovets."
    ),
    "btn_buy": "Buy treatment",
    # --- shop ----------------------------------------------------------------
    "products_body": "PCPB-registered products for *{disease}* from verified agrovets 👇",
    "btn_products": "See products",
    "no_products": (
        "No registered product for this problem is in stock near you right now. "
        "Please visit your nearest verified agrovet for advice."
    ),
    "product_detail": (
        "*{name}* {pack}\n🛡️ PCPB No: {pcpb}\n🧪 {ingredient}\n🏪 {agrovet}, {town}\n"
        "💰 KES {price}{discount}\n\n{usage}\n\nHow many do you need?"
    ),
    "discount": " (farmer discount {pct}% — was KES {old})",
    "order_summary": (
        "🧾 *Order summary*\n\n{qty} × {name} {pack}\nFrom: {agrovet}, {town}\n"
        "*Total: KES {amount}*\n\nPay with M-Pesa on *{phone}*?"
    ),
    "btn_pay_me": "Pay with this no.",
    "btn_pay_other": "Use another no.",
    "btn_cancel": "Cancel",
    "ask_pay_phone": "Type the M-Pesa number to pay with (e.g. 0712345678).",
    "bad_phone": "That doesn't look like a Safaricom number. Please type it like 0712345678.",
    "stk_sent": (
        "📲 Check your phone *{phone}* and enter your M-Pesa PIN to pay *KES {amount}*.\n\n"
        "I'll confirm here as soon as the payment is received."
    ),
    "stk_failed": "❌ Couldn't start the M-Pesa payment: {error}",
    "paid": (
        "✅ *Payment received!* Receipt: {receipt}\n\n"
        "Collect your {qty} × {name} at *{agrovet}*, {town}.\n{hint}\n\n"
        "🔑 Pickup code: *{code}*\nShow this code at the counter.\n\n"
        "📷 When you collect it, I'll ask you to photograph the label so we can check it's genuine."
    ),
    "pay_failed": "❌ The payment was not completed ({reason}).",
    "btn_retry_pay": "Try again",
    "order_wait": "⏳ Still waiting for your M-Pesa payment. Enter your PIN on the prompt, or type MENU to cancel.",
    # --- label check ---------------------------------------------------------
    "label_prompt": (
        "📦 *{agrovet}* has handed over your {name}.\n\n"
        "📷 Now send a clear photo of the product *label* showing the PCPB number — "
        "I'll check it's genuine. You can also type the number, e.g. *PCPB (CR) 1234*."
    ),
    "label_checking": "🔎 Checking the label against the PCPB register…",
    "label_verified": (
        "✅ *Verified genuine!*\n\n{name}\nPCPB No: {reg}\n"
        "Registered and exactly what was prescribed. You can use it safely — follow the label and wear gloves.\n\n"
        "🎁 +{points} points (total {total}). Use them for discounts at partner agrovets."
    ),
    "label_not_registered": (
        "⚠️ *Not a registered product. Do not use it.*\n\n"
        "The number on the label ({reg}) is not in the PCPB register. Keep the product and your receipt. "
        "We've flagged the store and will help you get a genuine product."
    ),
    "label_not_prescribed": (
        "⚠️ *Registered, but not what was prescribed.*\n\n"
        "The label shows {other} ({reg}), but your prescription is {name}. "
        "Please return it to the agrovet and ask for the right product."
    ),
    "label_unreadable": (
        "🤔 I couldn't read a PCPB number. Send a closer photo of the label, "
        "or type the number printed on it, e.g. *PCPB (CR) 1234*."
    ),
    # --- other menu items ----------------------------------------------------
    "history_empty": "You have no diagnoses or orders yet. Choose *Check my tomato* to start.",
    "history_title": "📋 *Your recent activity*",
    "agrovets_title": "🏪 *Verified agrovets in {county}*",
    "agrovets_none": "No verified agrovets are registered in {county} yet.",
    "profile": (
        "👤 *Your profile*\n\nName: {name}\nPhone: {phone}\nCounty: {county}\n"
        "Ward/Village: {ward}\nLanguage: {language}\n🎁 Points: {points}"
    ),
    "btn_language": "Change language",
    "language_set": "✅ Language updated.",
    "help": (
        "❓ *Help*\n\n"
        "• Type *MENU* anytime to see the main menu\n"
        "• Type *CANCEL* to stop what you're doing\n"
        "• To check your tomato: Menu → Check my tomato → send a photo\n"
        "• Payments are by M-Pesa — you only enter your PIN on your phone's M-Pesa prompt\n\n"
        "AgriSense never asks for your M-Pesa PIN in chat."
    ),
    "didnt_understand": "Sorry, I didn't get that. Please use the buttons, or type MENU.",
    # --- outcome follow-up ---------------------------------------------------
    "followup": "👋 {first}, did the treatment for *{disease}* on your {crop} work?",
    "btn_worked": "Yes, it worked",
    "btn_partly": "Partly",
    "btn_no_change": "No change",
    "outcome_thanks": "🙏 Thank you! Your answer helps other farmers choose treatments that work.",
    "outcome_no_change": (
        "😟 Sorry it didn't work. Send a new photo through *Check my tomato* "
        "and a verified agrovet will take a closer look."
    ),
}

SW = {
    # --- karibu na usajili ---------------------------------------------------
    "welcome": (
        "Karibu {name}! 👋\n\n"
        "Mimi ni msaidizi wa *AgriSense Hub* kwa wakulima wa nyanya. Ninakusaidia:\n"
        "🔍 Kuchunguza magonjwa ya nyanya kwa picha\n"
        "✅ Kupata utambuzi *uliothibitishwa na agrovet aliyeidhinishwa*\n"
        "🏪 Kununua dawa *halisi zilizosajiliwa na PCPB* karibu nawe — na kulipa kwa M-Pesa\n\n"
        "Tuanze kwa kukusajili. Inachukua takriban dakika 1."
    ),
    "btn_register": "Jisajili",
    "btn_how": "Inavyofanya kazi",
    "how_it_works": (
        "*AgriSense inavyofanya kazi* 🌱\n\n"
        "1️⃣ Tuma picha ya jani au tunda la nyanya lililo mgonjwa\n"
        "2️⃣ AI yetu inapendekeza tatizo ni nini\n"
        "3️⃣ *Agrovet aliyeidhinishwa* karibu nawe anaangalia picha na kuthibitisha\n"
        "4️⃣ Nunua dawa *iliyosajiliwa na PCPB* kutoka kwa agrovet aliyeidhinishwa kwa M-Pesa\n"
        "5️⃣ Piga picha ya lebo unapoichukua — tunathibitisha ni halisi na unapata pointi"
    ),
    "ask_name": "*Jina lako kamili* ni nani?",
    "bad_name": "Tafadhali andika jina lako kamili (angalau herufi 2).",
    "ask_county": "Asante, {first}! Shamba lako liko *kaunti* gani?",
    "btn_choose_county": "Chagua kaunti",
    "ask_county_text": "Tafadhali andika jina la kaunti yako.",
    "ask_ward": "Shamba liko *wadi au kijiji* gani?",
    "ask_language": "Unapendelea lugha gani?",
    "confirm_reg": (
        "Tafadhali thibitisha maelezo yako:\n\n"
        "👤 Jina: {name}\n📍 Kaunti: {county}\n🏘️ Wadi/Kijiji: {ward}\n"
        "🍅 Zao: Nyanya\n🗣️ Lugha: {language}\n\n"
        "🔒 Kwa kuthibitisha, unakubali AgriSense ihifadhi maelezo haya na picha za mimea yako "
        "ili kutambua magonjwa na kuboresha ushauri kwa wakulima walio karibu nawe."
    ),
    "btn_confirm": "Thibitisha ✅",
    "btn_edit": "Badilisha",
    "registered": "🎉 Umesajiliwa, {first}! Karibu AgriSense Hub.",
    # --- menyu kuu -----------------------------------------------------------
    "menu_body": "Habari {first}, ungependa kufanya nini leo?",
    "menu_button": "Fungua menyu",
    "menu_footer": "Andika MENU wakati wowote kurudi hapa",
    "sec_crop": "Afya ya mimea",
    "sec_shop": "Nunua na tafuta",
    "sec_account": "Akaunti",
    "row_diag": "🔍 Chunguza nyanya",
    "row_diag_d": "Tuma picha, upate utambuzi uliothibitishwa",
    "row_hist": "📋 Historia yangu",
    "row_hist_d": "Utambuzi na oda za awali",
    "row_agrovets": "🏪 Agrovet karibu nami",
    "row_agrovets_d": "Maduka yaliyoidhinishwa {county}",
    "row_profile": "👤 Wasifu wangu",
    "row_profile_d": "Maelezo yako, pointi na lugha",
    "row_help": "❓ Msaada",
    "row_help_d": "Jinsi ya kutumia AgriSense",
    "btn_menu": "Menyu kuu",
    # --- utambuzi ------------------------------------------------------------
    "ask_photo": (
        "📸 Tuma *picha moja iliyo wazi* ya jani au tunda la nyanya lililo mgonjwa.\n\n"
        "Vidokezo:\n• Piga mchana kwenye mwanga\n• Sogea karibu ili madoa yajaze picha\n• Shikilia simu bila kutikisika"
    ),
    "need_photo": "Tafadhali tuma *picha* 📸 — gusa alama ya 📎 au kamera.",
    "checking": "⏳ Ninachunguza picha ya nyanya yako… inachukua sekunde chache.",
    "diag_failed": "😕 Samahani, sikuweza kuchunguza picha sasa hivi. Tafadhali jaribu tena baada ya muda mfupi.",
    "not_clear": (
        "🤔 Sikuona mmea wa nyanya vizuri kwenye picha hiyo. "
        "Tafadhali tuma picha ya karibu zaidi na yenye mwanga ya jani lililo mgonjwa."
    ),
    "diag_ai_pending": (
        "🤖 *Pendekezo la AI:* {disease} (uhakika {pct}%)\n\n"
        "*Agrovet aliyeidhinishwa* karibu nawe sasa anaangalia picha yako ili kuthibitisha. "
        "Utapokea utambuzi uliothibitishwa na dawa ya kununua hapa hapa. 🙏"
    ),
    "diag_prevention": "🛡️ *Unaposubiri — fanya hivi sasa:*\n{prevention}",
    "btn_try_again": "Jaribu tena",
    "no_agrovet": "Bado hakuna agrovet aliyeidhinishwa {county}. Tutakujulisha mara tu atakapopatikana.",
    "agrovet_confirmed": (
        "✅ *Imethibitishwa na {agrovet}*\n\nNyanya yako ina *{disease}*.{note}\n\n"
        "Gusa *Nunua dawa* kuona dawa halisi zilizosajiliwa na PCPB kutoka kwa agrovet walioidhinishwa."
    ),
    "agrovet_corrected": (
        "📝 *Imeangaliwa na {agrovet}*\n\nAI haikuwa sahihi. Nyanya yako ina *{disease}*.{note}\n\n"
        "Gusa *Nunua dawa* kuona dawa halisi zilizosajiliwa na PCPB kutoka kwa agrovet walioidhinishwa."
    ),
    "btn_buy": "Nunua dawa",
    # --- duka ----------------------------------------------------------------
    "products_body": "Dawa zilizosajiliwa na PCPB kwa *{disease}* kutoka kwa agrovet walioidhinishwa 👇",
    "btn_products": "Ona dawa",
    "no_products": (
        "Hakuna dawa iliyosajiliwa kwa tatizo hili iliyo dukani karibu nawe sasa hivi. "
        "Tafadhali tembelea agrovet aliyeidhinishwa aliye karibu kwa ushauri."
    ),
    "product_detail": (
        "*{name}* {pack}\n🛡️ Nambari ya PCPB: {pcpb}\n🧪 {ingredient}\n🏪 {agrovet}, {town}\n"
        "💰 KES {price}{discount}\n\n{usage}\n\nUnahitaji ngapi?"
    ),
    "discount": " (punguzo la mkulima {pct}% — ilikuwa KES {old})",
    "order_summary": (
        "🧾 *Muhtasari wa oda*\n\n{qty} × {name} {pack}\nKutoka: {agrovet}, {town}\n"
        "*Jumla: KES {amount}*\n\nLipa kwa M-Pesa kupitia *{phone}*?"
    ),
    "btn_pay_me": "Lipa kwa nambari hii",
    "btn_pay_other": "Nambari nyingine",
    "btn_cancel": "Ghairi",
    "ask_pay_phone": "Andika nambari ya M-Pesa ya kulipia (mfano 0712345678).",
    "bad_phone": "Hiyo haionekani kuwa nambari ya Safaricom. Tafadhali iandike kama 0712345678.",
    "stk_sent": (
        "📲 Angalia simu yako *{phone}* na uweke PIN yako ya M-Pesa kulipa *KES {amount}*.\n\n"
        "Nitathibitisha hapa mara malipo yatakapopokelewa."
    ),
    "stk_failed": "❌ Sikuweza kuanzisha malipo ya M-Pesa: {error}",
    "paid": (
        "✅ *Malipo yamepokelewa!* Risiti: {receipt}\n\n"
        "Chukua {qty} × {name} kwa *{agrovet}*, {town}.\n{hint}\n\n"
        "🔑 Nambari ya kuchukua: *{code}*\nOnyesha nambari hii dukani.\n\n"
        "📷 Ukiichukua, nitakuomba upige picha ya lebo ili tuthibitishe ni halisi."
    ),
    "pay_failed": "❌ Malipo hayakukamilika ({reason}).",
    "btn_retry_pay": "Jaribu tena",
    "order_wait": "⏳ Bado ninasubiri malipo yako ya M-Pesa. Weka PIN kwenye ujumbe wa M-Pesa, au andika MENU kughairi.",
    # --- kuangalia lebo -------------------------------------------------------
    "label_prompt": (
        "📦 *{agrovet}* amekukabidhi {name}.\n\n"
        "📷 Sasa tuma picha iliyo wazi ya *lebo* ya dawa inayoonyesha nambari ya PCPB — "
        "nitathibitisha ni halisi. Unaweza pia kuandika nambari, mfano *PCPB (CR) 1234*."
    ),
    "label_checking": "🔎 Ninalinganisha lebo na rejista ya PCPB…",
    "label_verified": (
        "✅ *Imethibitishwa ni halisi!*\n\n{name}\nNambari ya PCPB: {reg}\n"
        "Imesajiliwa na ndiyo hasa uliyoandikiwa. Unaweza kuitumia kwa usalama — fuata lebo na vaa glavu.\n\n"
        "🎁 Pointi +{points} (jumla {total}). Zitumie kupata punguzo kwa agrovet washirika."
    ),
    "label_not_registered": (
        "⚠️ *Dawa hii haijasajiliwa. Usiitumie.*\n\n"
        "Nambari iliyo kwenye lebo ({reg}) haipo kwenye rejista ya PCPB. Hifadhi dawa na risiti yako. "
        "Tumeripoti duka hilo na tutakusaidia kupata dawa halisi."
    ),
    "label_not_prescribed": (
        "⚠️ *Imesajiliwa, lakini si uliyoandikiwa.*\n\n"
        "Lebo inaonyesha {other} ({reg}), lakini uliandikiwa {name}. "
        "Tafadhali irudishe kwa agrovet na uombe dawa sahihi."
    ),
    "label_unreadable": (
        "🤔 Sikuweza kusoma nambari ya PCPB. Tuma picha ya karibu zaidi ya lebo, "
        "au andika nambari iliyochapishwa, mfano *PCPB (CR) 1234*."
    ),
    # --- menyu nyingine ------------------------------------------------------
    "history_empty": "Bado huna utambuzi wala oda. Chagua *Chunguza nyanya* kuanza.",
    "history_title": "📋 *Shughuli zako za hivi karibuni*",
    "agrovets_title": "🏪 *Agrovet walioidhinishwa {county}*",
    "agrovets_none": "Bado hakuna agrovet walioidhinishwa {county}.",
    "profile": (
        "👤 *Wasifu wako*\n\nJina: {name}\nSimu: {phone}\nKaunti: {county}\n"
        "Wadi/Kijiji: {ward}\nLugha: {language}\n🎁 Pointi: {points}"
    ),
    "btn_language": "Badilisha lugha",
    "language_set": "✅ Lugha imebadilishwa.",
    "help": (
        "❓ *Msaada*\n\n"
        "• Andika *MENU* wakati wowote kuona menyu kuu\n"
        "• Andika *CANCEL* kusimamisha unachofanya\n"
        "• Kuchunguza nyanya: Menyu → Chunguza nyanya → tuma picha\n"
        "• Malipo ni kwa M-Pesa — unaweka PIN tu kwenye ujumbe wa M-Pesa kwenye simu yako\n\n"
        "AgriSense haitawahi kukuuliza PIN yako ya M-Pesa kwenye mazungumzo."
    ),
    "didnt_understand": "Samahani, sijaelewa. Tafadhali tumia vitufe, au andika MENU.",
    # --- ufuatiliaji -----------------------------------------------------------
    "followup": "👋 {first}, je, dawa ya *{disease}* kwenye {crop} yako ilifanya kazi?",
    "btn_worked": "Ndiyo, ilifanya",
    "btn_partly": "Kiasi",
    "btn_no_change": "Hakuna mabadiliko",
    "outcome_thanks": "🙏 Asante! Jibu lako linasaidia wakulima wengine kuchagua dawa zinazofanya kazi.",
    "outcome_no_change": (
        "😟 Pole, haikufanya kazi. Tuma picha mpya kupitia *Chunguza nyanya* "
        "na agrovet aliyeidhinishwa ataangalia kwa makini zaidi."
    ),
}

LANGS = {"en": EN, "sw": SW}


class _SafeDict(dict):
    def __missing__(self, key):
        return ""


def t(key, lang="en", **kw):
    text = LANGS.get(lang, EN).get(key) or EN.get(key, key)
    return text.format_map(_SafeDict(kw))
