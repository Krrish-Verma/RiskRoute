from app.database import SessionLocal, init_db
from app.services.crash_query_service import seed_demo_data


def main() -> None:
    init_db()
    with SessionLocal() as db:
        created = seed_demo_data(db)
    print(f"Seeded {created} demo crashes.")


if __name__ == "__main__":
    main()
