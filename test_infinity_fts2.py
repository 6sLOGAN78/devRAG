import infinity
from infinity.common import NetworkAddress
import time

client = infinity.connect(NetworkAddress("127.0.0.1", 23817))
db = client.get_database("test_fts")
table = db.get_table("fts_table")

try:
    # Try FTS search
    q = table.output(["id", "content", "_score"])
    q = q.match_text("content", "Redis", 10, None)
    res = q.to_pl()
    print("MATCH TEXT RESULTS for 'Redis':")
    print(res)
except Exception as e:
    print(f"Failed: {e}")
