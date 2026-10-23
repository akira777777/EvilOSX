#!/usr/bin/env python3
import sys

with open('cli.py', 'rb') as f:
    content = f.read()

# Заменяем буквальную последовательность \n (backslash + letter n) на реальный перенос строки после .format( в строке 319-322
old_pattern_319 = b'" (last seen: {})".format(\n                            str(i), bot.username, bot.hostname,'
new_pattern_319 = b'" (last seen: {})".format(\x0a                            str(i), bot.username, bot.hostname,'

if old_pattern_319 in content:
    print("Pattern 319 found! Replacing...")
    fixed_content = content.replace(old_pattern_319, new_pattern_319)
else:
    print("Pattern 319 NOT FOUND!")
    # Попробуем другой паттерн — буквальное \\n (backslash + letter n)
    old_pattern_319b = b'" (last seen: {})".format(\\n                            str(i), bot.username, bot.hostname,'
    new_pattern_319b = b'" (last seen: {})".format(\x0a                            str(i), bot.username, bot.hostname,'
    if old_pattern_319b in content:
        print("Pattern 319b found! Replacing...")
        fixed_content = content.replace(old_pattern_319b, new_pattern_319b)
    else:
        print("Pattern 319b NOT FOUND!")
        sys.exit(1)

# Заменяем буквальную последовательность \n (backslash + letter n) на реальный перенос строки после .format( в строке 339-342
old_pattern_339 = b'" (last seen: {})".format(\n                                str(i), bot.hostname,'
new_pattern_339 = b'" (last seen: {})".format(\x0a                                str(i), bot.hostname,'

if old_pattern_339 in content:
    print("Pattern 339 found! Replacing...")
    fixed_content = fixed_content.replace(old_pattern_339, new_pattern_339)
else:
    print("Pattern 339 NOT FOUND!")
    # Попробуем другой паттерн — буквальное \\n (backslash + letter n)
    old_pattern_339b = b'" (last seen: {})".format(\\n                                str(i), bot.hostname,'
    new_pattern_339b = b'" (last seen: {})".format(\x0a                                str(i), bot.hostname,'
    if old_pattern_339b in fixed_content:
        print("Pattern 339b found! Replacing...")
        fixed_content = fixed_content.replace(old_pattern_339b, new_pattern_339b)
    else:
        print("Pattern 339b NOT FOUND!")

# Проверяем что замены сработали
print("\nVerification:")
with open('cli.py', 'rb') as f:
    content2 = f.read()
idx1 = content2.find(b'" (last seen: {})".format(\x0a                            str(i), bot.username, bot.hostname,')
print("Pattern 319 with \\x0a found:", idx1 != -1)
idx2 = content2.find(b'" (last seen: {})".format(\x0a                                str(i), bot.hostname,')
print("Pattern 339 with \\x0a found:", idx2 != -1)

# Проверяем AST parse
import ast
try:
    tree = ast.parse(content2.decode('utf-8'))
    print("AST parse OK!")
except SyntaxError as e:
    print(f"SyntaxError at line {e.lineno}: {e.msg}")

with open('cli.py', 'wb') as f:
    f.write(fixed_content)
print("\nFile saved successfully!")
