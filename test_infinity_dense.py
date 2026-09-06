import infinity
from infinity.common import NetworkAddress
client = infinity.connect(NetworkAddress("127.0.0.1", 23817))
db = client.get_database("test_fts")
table = db.get_table("fts_table")
# oh wait, test_fts doesn't have an embedding column. Let's query test_dataset_123.
db_default = client.get_database("default_db")
table2 = db_default.get_table("idx_test_dataset_123")
q = table2.output(["id"])
# create dummy vector of dim 384
q = q.match_dense("embedding", [0.1]*384, "float", "cosine", 10)
print(q.to_pl())
