import sqlite3

db = sqlite3.connect('data.db')
cur = db.cursor()
cur.execute("select count(*), min(timestamp), max(timestamp) from checks where target_name=?", ('Digikala',))
print('Digikala:', cur.fetchone())
cur.execute("select count(*), min(timestamp), max(timestamp) from checks where target_name=?", ('GitHub',))
print('GitHub:', cur.fetchone())
cur.execute("select count(*) from checks")
print('Total checks:', cur.fetchone())
cur.close()
