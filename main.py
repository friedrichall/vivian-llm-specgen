# This is a sample Python script.
import asyncio
from dotenv import load_dotenv

from vivian_pipeline.agents_vivian import agents_vivian


# Press Umschalt+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.


async def main():
    await agents_vivian()

if __name__ == '__main__':
    load_dotenv()
    asyncio.run(main())


