"""Debug: test DeepSeek API endpoint."""
import json, os, urllib.request

key = os.environ.get("DEEPSEEK_API_KEY", "")
model = "deepseek-chat"
prompt = "Say 'hello' in one word."

urls = [
    "https://api.deepseek.com/chat/completions",
    "https://api.deepseek.com/v1/chat/completions",
]

for url in urls:
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 10,
    }).encode()
    try:
        req = urllib.request.Request(url, data=payload, headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        })
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        text = data["choices"][0]["message"]["content"]
        print(f"✅ {url}  →  {text}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        print(f"❌ {url}  →  HTTP {e.code}: {body}")
    except Exception as e:
        print(f"❌ {url}  →  {e}")
