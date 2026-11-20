import html, re, sys

src = r"E:\Proyecto X\research\reascripthelp.html"
dst = r"E:\Proyecto X\research\reascripthelp.txt"

with open(src, "r", encoding="utf-8", errors="replace") as f:
    s = f.read()

# drop script/style blocks
s = re.sub(r"(?is)<script.*?</script>", " ", s)
s = re.sub(r"(?is)<style.*?</style>", " ", s)

# block-level boundaries -> newlines
s = re.sub(r"(?i)</(tr|p|div|h[1-6]|table|ul|li|pre)>", "\n", s)
s = re.sub(r"(?i)<br\s*/?>", "\n", s)
s = re.sub(r"(?i)</t[dh]>", "\t", s)
# remove remaining tags
s = re.sub(r"(?s)<[^>]+>", "", s)
s = html.unescape(s)
# normalize horizontal whitespace, keep newlines
lines = []
for ln in s.split("\n"):
    ln = ln.replace("\t", " ")
    ln = re.sub(r"[ \r\f\v]+", " ", ln).strip()
    lines.append(ln)
out = []
prev_blank = False
for ln in lines:
    if not ln:
        if prev_blank:
            continue
        prev_blank = True
    else:
        prev_blank = False
    out.append(ln)
text = "\n".join(out)
with open(dst, "w", encoding="utf-8") as f:
    f.write(text)
print("lines:", text.count("\n"), "chars:", len(text))
