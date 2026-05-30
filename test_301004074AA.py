# test_301004074AA.py
from utils.db import get_connection
conn = get_connection()
c = conn.cursor()
c.execute("SELECT product_code, required_date, parent_chain, bom_level, team_name FROM production_requirements WHERE product_code LIKE '%301004074AA%' ORDER BY parent_chain")
print("301004074AA family (sorted by parent_chain):")
for r in c.fetchall():
    print(f"  L{r[3]} {r[0]:45s} date={r[1]} team={r[4]} chain={r[2]}")
conn.close()
