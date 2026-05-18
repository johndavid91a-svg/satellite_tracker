import asyncio
import httpx

async def test():
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        r = await client.get("https://tle.ivanstanojevic.me/api/tle/", params={
            "search": "ISS",
            "page-size": 20,
            "page": 1,
        })
        print("Status:", r.status_code)
        data = r.json()
        print("Keys:", list(data.keys()))
        members = data.get("member", [])
        print("Members count:", len(members))
        if members:
            print("First member keys:", list(members[0].keys()))
            print("First member:", members[0])

asyncio.run(test())
