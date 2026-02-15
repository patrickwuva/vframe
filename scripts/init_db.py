import sys
from pathlib import Path

# Allow running this script directly from a fresh checkout.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from frameapp import create_app
from frameapp.db import init_db


def main() -> None:
    app = create_app(start_background_worker=False)
    with app.app_context():
        init_db()
    print("Database initialized")


if __name__ == "__main__":
    main()
