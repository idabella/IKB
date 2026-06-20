import urllib.request
import json

BASE = "http://localhost:3000"

def get(path):
    with urllib.request.urlopen(BASE + path) as r:
        return json.loads(r.read())

print("=== Health ===")
h = get("/api/health")
print(h)

print("\n=== KPIs ===")
k = get("/api/dashboard/kpis")
print(k)

print("\n=== Machines ===")
m = get("/api/machines")
print("Count:", len(m))
print("First:", m[0]["name"], "status=", m[0]["status"])

print("\n=== Alerts ===")
a = get("/api/alerts")
print("Count:", len(a))
print("First:", a[0]["machine"], "severity=", a[0]["severity"])

print("\n=== Documents ===")
d = get("/api/documents")
print("Count:", len(d))
print("First:", d[0]["title"][:50])

print("\n=== Vibration ===")
v = get("/api/dashboard/vibration")
print("Machine:", v["machine_name"], "points:", len(v["data"]), "threshold:", v["threshold"])

print("\n=== Insights ===")
i = get("/api/dashboard/insights")
print("Count:", len(i))

print("\nAll endpoints OK!")
