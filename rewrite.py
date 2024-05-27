with open('series/1/out.txt', 'r', encoding='cp1252') as f:
  txt = f.read()
with open('series/1/out.txt', 'w', encoding='utf-8') as f:
  f.write(txt)
