import sys

from pixel_skill.cli import app

if __name__ == "__main__":
    sys.argv.insert(1, "validate")
    app()
