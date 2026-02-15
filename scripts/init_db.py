from frameapp import create_app
from frameapp.db import init_db


def main() -> None:
    app = create_app(start_background_worker=False)
    with app.app_context():
        init_db()
    print("Database initialized")


if __name__ == "__main__":
    main()
