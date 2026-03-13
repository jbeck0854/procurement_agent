from psycopg2 import connect

from config import DATABASE_URL


def get_connection():
    return connect(DATABASE_URL)


if __name__ == "__main__":
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM dim_supplier;")
        print(cur.fetchone()[0])
    conn.close()
