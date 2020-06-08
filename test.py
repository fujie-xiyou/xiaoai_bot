import asyncio
import time

async def test2():
    print(2)

async def test():
    print("1")
    time.sleep(3)
    await test2()

if __name__ == '__main__':
    asyncio.run(test())