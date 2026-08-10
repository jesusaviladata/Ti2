import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_refresh_reuse_revokes_the_whole_session(use_memory_session_store):
    store = use_memory_session_store
    session = await store.create("user-1", "tenant-1")

    new_jti, _ = await store.rotate(session.sid, session.refresh_jti)
    assert new_jti != session.refresh_jti

    with pytest.raises(HTTPException) as reused:
        await store.rotate(session.sid, session.refresh_jti)

    assert reused.value.status_code == 401
    assert await store.validate(session.sid, "user-1") is False
