import psycopg2

conn = psycopg2.connect("postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv")
cur = conn.cursor()

# Check enum values
cur.execute("SELECT unnest(enum_range(NULL::documenttype));")
print("Enum values:", cur.fetchall())

# Check table columns
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'knowledge_bases';")
print("Columns:", cur.fetchall())