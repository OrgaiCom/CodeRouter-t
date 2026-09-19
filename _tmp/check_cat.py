import httpx

try:
    r = httpx.get("http://127.0.0.1:8080/v1/models", timeout=2.0)
    print("models status:", r.status_code)
    print("models json:", r.json())
except Exception as e:
    print("error connecting to 8080:", e)
