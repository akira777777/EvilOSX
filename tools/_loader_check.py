"""Ad-hoc checks for --loader default validation (deleted after use)."""
import sys

sys.path.insert(0, r"c:\Users\novra\Desktop\EvilOSX")
import start  # noqa: E402


def run(argv):
    try:
        return start.main(argv)
    except SystemExit as exc:
        return exc.code


print("1 missing --host      ->", run(["--builder", "--no-banner"]))
print("2 unknown --loader    ->", run(["--builder", "--host", "1.2.3.4",
                                      "--loader", "nope", "--no-banner"]))

start.available_loaders = lambda: []  # simulate bot/loaders being empty
print("3 missing default     ->", run(["--builder", "--host", "1.2.3.4",
                                       "--no-banner"]))
print("4 server mode no loaders ->", run(["--db-path",
                                         r"C:\nonexistent-dir\x.db",
                                         "--no-banner"]))
