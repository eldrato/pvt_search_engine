import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_root_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["app"] == "Aegis Search & Research Engine"
        assert data["status"] == "online"
        assert "version" in data


@pytest.mark.asyncio
async def test_health_endpoint_schema():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Request health check endpoint
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()

        # Validate top-level health keys
        assert "status" in data
        assert data["status"] in ["healthy", "degraded", "unreachable"]
        assert "version" in data
        assert "services" in data

        # Check expected services
        services = data["services"]
        for svc_name in ["postgres", "opensearch", "qdrant", "redis"]:
            assert svc_name in services
            svc_info = services[svc_name]
            assert "status" in svc_info
            assert "latency_ms" in svc_info
            assert isinstance(svc_info["latency_ms"], (int, float))
