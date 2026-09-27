"""Static consistency checks: dead onclick handlers + i18n key coverage."""
import re, glob, os

JS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "js")
src = ""
files = sorted(glob.glob(os.path.join(JS_DIR, "*.js")))
for f in files:
    src += open(f).read() + "\n"

# --- 1. onclick handlers used in generated HTML vs functions defined ---
handlers = set(re.findall(r'onclick=(?:"|\')\s*(\w+)\s*\(', src))
defs = set()
for m in re.finditer(r'\bfunction\s+(\w+)\s*\(', src):
    defs.add(m.group(1))
for m in re.finditer(r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+function|async\s*\(|function|\()', src):
    defs.add(m.group(1))
builtins_ok = {"if", "for", "while", "return", "switch", "catch"}
dead = sorted(h for h in handlers if h not in defs and h not in builtins_ok)
print(f"onclick handlers used: {len(handlers)}")
print(f"DEAD handlers (no definition found): {dead if dead else 'NONE - all wired'}")

# --- 2. i18n: keys used via t('key') / t(\"key\") vs keys defined in i18n.js ---
used = set(re.findall(r'\bt\(\s*["\']([A-Za-z0-9_]+)["\']\s*\)', src))
i18n_path = os.path.join(JS_DIR, "i18n.js")
i18n_src = open(i18n_path).read()
keys = set(re.findall(r'^\s{2}([A-Za-z0-9_]+):\s*\{', i18n_src, re.M))
missing = sorted(k for k in used if k not in keys)
unused = sorted(k for k in keys if k not in used)
print(f"\ni18n keys used across views: {len(used)}")
print(f"MISSING from pack (would render undefined): {missing if missing else 'NONE - complete'}")
print(f"defined but unused: {len(unused)} {unused[:10]}")

ok = not dead and not missing
print("\nRESULT:", "CLEAN" if ok else "ISSUES FOUND")
raise SystemExit(0 if ok else 1)
