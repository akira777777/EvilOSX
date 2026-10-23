import os
import sys


def demo():
    if os.name == "posix":
        print("posix only")
    if sys.platform == "darwin":
        print("mac only")
    return 1


print(demo())
