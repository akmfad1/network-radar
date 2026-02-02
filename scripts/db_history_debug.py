import sqlite3
from datetime import datetime, timedelta

db = sqlite3.connect('data.db')
cur = db.cursor()
cutoff = (datetime.utcnow() - timedelta(hours=1)).isoformat()
cur.execute("select agent_id, target_name, host, type, status, latency_ms, timestamp, error, details from checks where target_name = ? and timestamp >= ? order by timestamp asc", ('Digikala', cutoff))
rows = cur.fetchall()
print('rows:', len(rows))
for r in rows[-10:]:
    print(r)
cur.close()
