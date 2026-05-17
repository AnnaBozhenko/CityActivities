import asyncio
from worker import fetch_news_task

async def main():
    # This sends a "one-off" job to the worker immediately
    await fetch_news_task.kiq(source_type="tg")
    print("Task pushed to worker!")

if __name__ == "__main__":
    asyncio.run(main())