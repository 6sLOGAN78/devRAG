import infinity
from infinity.common import NetworkAddress
from infinity.index import IndexInfo, IndexType
from infinity.common import ConflictType

client = infinity.connect(NetworkAddress("127.0.0.1", 23817))
client.create_database("test_fts", ConflictType.Ignore)
db = client.get_database("test_fts")
schema = {
    "id": {"type": "varchar"},
    "content": {"type": "varchar"}
}
db.create_table("fts_table", schema, ConflictType.Ignore)
table = db.get_table("fts_table")

# Create Fulltext index
try:
    idx_info = IndexInfo("content", IndexType.FullText, {})
    table.create_index("fts_idx", idx_info, ConflictType.Ignore)
    
    table.insert([{"id": "1", "content": "Distributed locks prevent multiple workers from modifying the same task."}])
    table.insert([{"id": "2", "content": "Redis provides a locking mechanism for coordinating workers."}])
    table.insert([{"id": "3", "content": "PostgreSQL stores relational document metadata."}])
    table.insert([{"id": "4", "content": "RedisDistributedLock(\"update_progress\")"}])
    
    # Try FTS search
    q = table.output(["id", "content", "_score"])
    q = q.match_text("content", "RedisDistributedLock update_progress", 10, None)
    res = q.to_pl()
    print("MATCH TEXT RESULTS:")
    print(res)
except Exception as e:
    print(f"Failed: {e}")
