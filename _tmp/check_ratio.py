import re
texts = [
    'The word "こんにちは" means hello.',
    "Please review the document regarding 設計 and 仕様.",
    "CodeRouterプロジェクトについて、何か取り組むべきタスクはありますか？",
    "こんにちは。またお呼びいただきありがとうございます。",
    "Hello again! Please let me know how I can assist you with the CodeRouter project today.",
]
ja_re = re.compile(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]")
en_re = re.compile(r"[A-Za-z]")
for t in texts:
    ja = len(ja_re.findall(t))
    en = len(en_re.findall(t))
    total = ja + en
    ratio = ja / total if total else 0
    print(f"ja={ja:3d} en={en:3d} ratio={ratio:.3f}  | {t[:60]}")
