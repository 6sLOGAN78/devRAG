import mysql.connector
import uuid

conn = mysql.connector.connect(host="127.0.0.1", port=13306, user="ragflow", password="ragflow", database="rag_flow")
cur = conn.cursor()

# Get the latest pending document
cur.execute("SELECT id, tenant_id FROM document WHERE parse_status = 'pending' ORDER BY created_at DESC LIMIT 1")
row = cur.fetchone()
if not row:
    print("No pending document found")
    exit(1)
doc_id, tenant_id = row

task_id = str(uuid.uuid4())
cur.execute("""
    INSERT INTO document_task (id, document_id, tenant_id, status, progress, created_at, updated_at) 
    VALUES (%s, %s, %s, 'unstart', 0, NOW(), NOW())
""", (task_id, doc_id, tenant_id))
conn.commit()
print(f"Created task {task_id} for document {doc_id}")
