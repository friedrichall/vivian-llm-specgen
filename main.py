# Minimal CLI entry point for running the Vivian pipeline.
import asyncio

from dotenv import load_dotenv

from vivian_pipeline.pipeline_orchestrator import PipelineConfig, run_pipeline_async


async def main():
    config = PipelineConfig.default()
    result = await run_pipeline_async(config)
    print(f"Pipeline finished: success={result.success}, attempts={result.attempts_completed}")


if __name__ == '__main__':
    load_dotenv()
    asyncio.run(main())
