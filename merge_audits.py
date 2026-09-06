import re

def parse_sections(filename):
    with open(filename, 'r') as f:
        content = f.read()
    
    sections = {}
    # Split by ## [number]. 
    parts = re.split(r'(?m)^## (\d+\.\s+.*)$', content)
    
    header = parts[0].strip()
    
    for i in range(1, len(parts), 2):
        sec_title = parts[i].strip()
        sec_content = parts[i+1].strip()
        sections[sec_title] = sec_content
        
    return header, sections

h1, s1 = parse_sections('audit1.md')
h2, s2 = parse_sections('audit2.md')

all_titles = list(s1.keys())
for t in s2.keys():
    if t not in all_titles:
        all_titles.append(t)

with open('audit_merged.md', 'w') as f:
    f.write(f"{h1}\n\n")
    
    for title in all_titles:
        f.write(f"## {title}\n\n")
        
        c1 = s1.get(title, "")
        c2 = s2.get(title, "")
        
        if c1 and c2:
            if c1 == c2:
                f.write(f"{c1}\n\n")
            else:
                f.write("### Analysis A (From Audit 1)\n")
                f.write(f"{c1}\n\n")
                f.write("### Analysis B (From Audit 2)\n")
                f.write(f"{c2}\n\n")
        elif c1:
            f.write(f"{c1}\n\n")
        elif c2:
            f.write(f"{c2}\n\n")

print("Merged successfully into audit_merged.md")
