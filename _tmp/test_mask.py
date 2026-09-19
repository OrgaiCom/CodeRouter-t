from coderouter.jp_translation.masking import mask_text, has_placeholder_mutation, unmask_text

text = "Hello again! Please let me know how I can assist you with the CodeRouter project today, whether it's implementing a new safeguard, refining the routing mechanism, or tackling a specific bug. I'm ready when you are!"
masked, mapping = mask_text(text)
print("masked:", masked)
print("mapping:", mapping)
