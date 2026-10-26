"""Entry point: `python main.py` (or the built MarshallIX9.exe)."""
import sys


def main() -> int:
    if "--selftest" in sys.argv:
        from marshall_ix9.selftest import run_selftest

        return run_selftest(sys.argv)
    from marshall_ix9.app import run

    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
