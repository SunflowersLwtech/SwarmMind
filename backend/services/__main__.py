"""Entry point: python -m backend.services

Starts the MCP tool server using uvicorn directly for fast subprocess startup.
Heavy imports (GridWorld, numpy, scipy) are deferred to lifespan.
"""
