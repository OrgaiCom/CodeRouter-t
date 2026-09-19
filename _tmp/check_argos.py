try:
    import argostranslate.translate
    installed_languages = argostranslate.translate.get_installed_languages()
    print("Installed languages:", [l.code for l in installed_languages])
    en = [l for l in installed_languages if l.code == "en"]
    ja = [l for l in installed_languages if l.code == "ja"]
    if en and ja:
        en_to_ja = en[0].get_translation(ja[0])
        print("en_to_ja:", en_to_ja)
        text = "Hello again! Please let me know how I can assist you with the __CR_PROTECTED_0__ project today, whether it's implementing a new safeguard, refining the routing mechanism, or tackling a specific bug. I'm ready when you are!"
        res = en_to_ja.translate(text)
        print("Argos translated:", res)
except Exception as e:
    print("Error:", e)
