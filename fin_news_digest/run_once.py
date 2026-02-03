import argparse

from fin_news_digest.digest import run_digest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--edition", default="Manual", help="Edition label")
    args = parser.parse_args()
    run_digest(args.edition)


if __name__ == "__main__":
    main()
