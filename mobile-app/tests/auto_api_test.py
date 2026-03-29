"""OpenAPI 기반 API 자동 탐지 테스트"""
import sys
import json
import urllib.request
import urllib.error

backend = sys.argv[1]
sample_pnu = sys.argv[2] if len(sys.argv) > 2 else ""

# openapi.json 로드
try:
    resp = urllib.request.urlopen(f"{backend}/openapi.json", timeout=5)
    openapi = json.loads(resp.read())
except Exception as e:
    print(f"\033[31m✗ openapi.json 로드 실패: {e}\033[0m")
    print("RESULT:0:1")
    sys.exit(0)

paths = openapi.get("paths", {})
pass_count = 0
fail_count = 0

# 스킵 (스트리밍/업로드 등)
SKIP = {"/api/chat/stream", "/api/chat", "/api/knowledge/upload"}

# POST 최소 body
POST_BODIES = {
    "/api/nudge/score": '{"nudges":["cost"],"weights":null,"top_n":3,"keywords":["강남"]}',
    "/api/commute": '{"origin":"강남역","destinations":["서울역"]}',
    "/api/chat/feedback": '{"user_message":"t","assistant_message":"t","rating":1}',
}

for path, methods in sorted(paths.items()):
    if path in SKIP:
        continue

    for method in methods:
        mu = method.upper()
        if mu not in ("GET", "POST"):
            continue

        # path parameter 치환
        url_path = path
        if "{pnu}" in url_path:
            if not sample_pnu:
                continue
            url_path = url_path.replace("{pnu}", sample_pnu)
        if "{doc_id}" in url_path:
            continue

        url = backend + url_path
        if url_path == "/api/apartments/search":
            url += "?q=test"
        if url_path == "/api/commute/search":
            url += "?q=test"

        try:
            if mu == "GET":
                req = urllib.request.Request(url)
            else:
                body = POST_BODIES.get(path, "{}").encode()
                req = urllib.request.Request(
                    url, data=body, headers={"Content-Type": "application/json"}
                )
            resp = urllib.request.urlopen(req, timeout=10)
            code = resp.getcode()
            print(f"\033[32m✓ [자동] {mu} {path} → {code}\033[0m")
            pass_count += 1
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500:
                print(f"\033[32m✓ [자동] {mu} {path} → {e.code} (서버 응답)\033[0m")
                pass_count += 1
            else:
                print(f"\033[31m✗ [자동] {mu} {path} → {e.code}\033[0m")
                fail_count += 1
        except Exception as e:
            print(f"\033[31m✗ [자동] {mu} {path} → {type(e).__name__}\033[0m")
            fail_count += 1

print(f"RESULT:{pass_count}:{fail_count}")
