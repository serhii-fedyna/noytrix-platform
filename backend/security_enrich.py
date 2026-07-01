from typing import Dict, Any
import httpx


async def google_safe_browsing_check(url: str, api_key: str) -> Dict[str, Any]:
    if not api_key:
        return {"status": "not_configured", "comment": "Safe Browsing key not set."}
    try:
        body = {
            "client": {"clientId": "noytrix", "clientVersion": "1.0"},
            "threatInfo": {
                "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"],
                "platformTypes": ["ANY_PLATFORM"],
                "threatEntryTypes": ["URL"],
                "threatEntries": [{"url": url}],
            },
        }
        api = f"https://safebrowsing.googleapis.com/v4/threatMatches:find?key={api_key}"
        async with httpx.AsyncClient(timeout=10.0) as cl:
            r = await cl.post(api, json=body)
            r.raise_for_status()
            j = r.json() or {}
            matches = j.get("matches") or []
            if matches:
                return {"status": "warn", "comment": "Google Safe Browsing: threat match found.", "matches": matches[:3]}
            return {"status": "ok", "comment": "Google Safe Browsing: no matches."}
    except Exception as e:
        return {"status": "error", "comment": f"Safe Browsing error: {e}"}


async def urlscan_submit(url: str, api_key: str) -> Dict[str, Any]:
    if not api_key:
        return {"status": "not_configured", "comment": "urlscan key not set."}
    try:
        headers = {"API-Key": api_key, "Content-Type": "application/json"}
        payload = {"url": url, "visibility": "unlisted"}
        async with httpx.AsyncClient(timeout=15.0) as cl:
            r = await cl.post("https://urlscan.io/api/v1/scan/", headers=headers, json=payload)
            r.raise_for_status()
            j = r.json() or {}
            return {"status": "queued", "comment": "urlscan submitted.", "result": j}
    except Exception as e:
        return {"status": "error", "comment": f"urlscan error: {e}"}


async def virustotal_check(url: str, api_key: str) -> Dict[str, Any]:
    if not api_key:
        return {"status": "not_configured", "comment": "VT key not set."}
    try:
        async with httpx.AsyncClient(timeout=15.0) as s:
            r = await s.post(
                "https://www.virustotal.com/api/v3/urls",
                headers={"x-apikey": api_key},
                data={"url": url},
            )
            r.raise_for_status()
            rid = r.json()["data"]["id"]

            r2 = await s.get(
                f"https://www.virustotal.com/api/v3/analyses/{rid}",
                headers={"x-apikey": api_key},
            )
            j = r2.json() or {}
            stats = (j.get("data", {}).get("attributes", {}).get("stats") or {})
            mal = int(stats.get("malicious", 0) or 0)
            susp = int(stats.get("suspicious", 0) or 0)
            if mal > 0 or susp > 0:
                return {"status": "warn", "comment": f"VirusTotal: hits ({mal} malicious, {susp} suspicious).", "stats": stats}
            return {"status": "ok", "comment": "VirusTotal: no hits.", "stats": stats}
    except Exception as e:
        return {"status": "error", "comment": f"VirusTotal error: {e}"}