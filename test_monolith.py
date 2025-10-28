import httpx
import asyncio

async def test_monolith():
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get('http://monolith:8000/health')
            print(f"Health Status: {response.status_code}")
            
            # Test price data
            response = await client.get('http://monolith:8000/prices?symbol=XAUUSD=X&start=2024-01-01')
            print(f"Price Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Data points: {len(data.get('data', []))}")
            else:
                print(f"Error: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(test_monolith())
