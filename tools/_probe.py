import subprocess

src = subprocess.run(
    ["git", "show", "HEAD:start.py"],
    cwd=r"c:\Users\novra\Desktop\EvilOSX",
    capture_output=True,
).stdout.decode("utf-8")
lines = src.splitlines()
print("HEAD total lines:", len(lines))
for i in range(325, 342):
    print("%4d| %r" % (i + 1, lines[i]))
print("--- platform-ish lines ---")
for i, line in enumerate(lines):
    if "os.name" in line or "sys.platform" in line or "if __name__" in line:
        print("%4d| %s" % (i + 1, line))
