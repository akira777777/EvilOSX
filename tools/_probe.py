import subprocess

REPO = r"c:\Users\novra\Desktop\EvilOSX"


def show(rev):
    return subprocess.run(["git", "show", rev + ":start.py"], cwd=REPO,
                          capture_output=True).stdout.decode("utf-8")


for rev in ("HEAD", "e3903fc", "548f56f"):
    src = show(rev)
    lines = src.splitlines()
    markers = [i + 1 for i, l in enumerate(lines) if "stamp = datetime.now()" in l]
    print(rev, "lines:", len(lines), "print-based output at:", markers)


cand = show("548f56f").splitlines()
if len(cand) > 340:
    print("--- 548f56f lines 325-345 ---")
    for i in range(324, 345):
        print("%4d| %r" % (i + 1, cand[i]))
