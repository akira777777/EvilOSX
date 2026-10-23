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
    # Попробуем найти буквальную последовательность \n (backslash + letter n)
    literal_backslash_n = b'\\n'
    
    # Ищем буквальное \\n после .format( в строке 319-322
    pos_319 = content.find(b'" (last seen: {})".format(')
    print("Position of pattern in line 319:", pos_319 if pos_319 != -1 else "NOT FOUND")
    
    if pos_319 != -1:
        after_format2 = pos_319 + len(b'" (last seen: {})".format(')
        print("After .format( at position", after_format2, "byte=", repr(content[after_format2]), "(ord={})".format(content[after_format2]))
        
        # Ищем буквальное \\n после этой позиции
        literal_n_pos = content.find(literal_backslash_n, after_format2)
        print("Literal \\n found at position:", literal_n_pos if literal_n_pos != -1 else "NOT FOUND")
        
        if literal_n_pos != -1:
            # Находим конец строки 321 (перед strftime)
            end_of_line = content.find(b')', literal_n_pos + 20)
            print("End of line at position:", end_of_line)
            
            # Заменяем буквальное \\n на реальный перенос строки
            fixed_content = content[:literal_n_pos] + b'\x0a' + content[literal_n_pos+1:end_of_line] + content[end_of_line:]
            print("Replaced literal \\n with real newline!")
        else:
            print("Literal \\n NOT FOUND after .format( in line 319!")
    else:
        print("Pattern for line 319 NOT FOUND!")

# Заменяем буквальную последовательность \n (backslash + letter n) на реальный перенос строки после .format( в строке 339-342
old_pattern_339 = b'" (last seen: {})".format(\n                                str(i), bot.hostname,'

new_pattern_339 = b'" (last seen: {})".format(\x0a                                str(i), bot.hostname,'

if old_pattern_339 in fixed_content:
    print("Pattern 339 found! Replacing...")
    fixed_content = fixed_content.replace(old_pattern_339, new_pattern_339)
else:
    print("Pattern 339 NOT FOUND!")
    # Попробуем найти буквальную последовательность \n (backslash + letter n)
    literal_backslash_n = b'\\n'
    
    # Ищем буквальное \\n после .format( в строке 339-342
    pos_339 = content.find(b'" (last seen: {})".format(', pos_319 + 200) if 'pos_319' in dir() else -1
    print("Position of pattern in line 339:", pos_339 if pos_339 != -1 else "NOT FOUND")
    
    if pos_339 != -1:
        after_format2 = pos_339 + len(b'" (last seen: {})".format(')
        print("After .format( at position", after_format2, "byte=", repr(content[after_format2]), "(ord={})".format(content[after_format2]))
        
        # Ищем буквальное \\n после этой позиции
        literal_n_pos = content.find(literal_backslash_n, after_format2)
        print("Literal \\n found at position:", literal_n_pos if literal_n_pos != -1 else "NOT FOUND")
        
        if literal_n_pos != -1:
            # Находим конец строки 341 (перед закрывающей скобкой)
            end_of_line = content.find(b')', literal_n_pos + 20)
            print("End of line at position:", end_of_line)
            
            # Заменяем буквальное \\n на реальный перенос строки
            fixed_content = fixed_content[:literal_n_pos] + b'\x0a' + content[literal_n_pos+1:end_of_line] + content[end_of_line:]
            print("Replaced literal \\n with real newline!")
        else:
            print("Literal \\n NOT FOUND after .format( in line 339!")
    else:
        print("Pattern for line 339 NOT FOUND!")

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
