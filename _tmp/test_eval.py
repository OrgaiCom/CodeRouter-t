from coderouter.jp_translation.masking import is_already_japanese, is_japanese, is_pure_japanese

text = "Hello again! Please let me know how I can assist you with the CodeRouter project today, whether it's implementing a new safeguard, refining the routing mechanism, or tackling a specific bug. I'm ready when you are!"

print("is_already_japanese:", is_already_japanese(text))
print("is_japanese:", is_japanese(text))
print("is_pure_japanese:", is_pure_japanese(text))
