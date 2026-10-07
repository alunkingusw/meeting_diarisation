from datetime import date


def _chunk(meeting_id, meeting_date, start_sec, text):
    return {
        "chunk_id": f"{meeting_id}_{start_sec:05d}", "meeting_id": str(meeting_id), "meeting_title": "Team A",
        "meeting_date": meeting_date, "speaker": "Alice", "text": text, "start_ts": "00:00:01.000",
        "end_ts": "00:00:09.000", "start_sec": float(start_sec), "meeting_ts": _ts(meeting_date),
    }


def _ts(day):
    from backend.transcript_rag.indexer import meeting_date_ts

    return meeting_date_ts(day)


def test_meeting_date_ts_parses_dates_and_ignores_garbage():
    from backend.transcript_rag.indexer import meeting_date_ts

    assert meeting_date_ts("2026-10-01") == 1790812800
    assert meeting_date_ts("2026-10-01T09:30:00") == 1790812800
    assert meeting_date_ts("unknown") is None


def test_chunks_in_window_filters_orders_and_caps(tmp_path, monkeypatch):
    import chromadb

    from backend.transcript_rag import vectorstore
    from backend.transcript_rag.indexer import transcripts_in_window

    client = chromadb.PersistentClient(path=str(tmp_path))
    monkeypatch.setattr(vectorstore, "get_chroma_client", lambda: client)
    collection = client.get_or_create_collection(vectorstore.transcripts_collection_name("Team A"))
    chunks = [
        _chunk(1, "2026-09-01", 0, "too early"),
        _chunk(3, "2026-09-10", 0, "later meeting"),
        _chunk(2, "2026-09-08", 30, "second"),
        _chunk(2, "2026-09-08", 0, "first"),
        _chunk(4, "2026-09-15", 0, "end is exclusive"),
    ]
    collection.upsert(
        ids=[c["chunk_id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=chunks,
        embeddings=[[1.0, 0.0, 0.0]] * len(chunks),
    )

    window = transcripts_in_window("Team A", date(2026, 9, 7), date(2026, 9, 15), limit=10)
    assert [c["text"] for c in window] == ["first", "second", "later meeting"]

    assert transcripts_in_window("Team A", date(2026, 9, 7), date(2026, 9, 15), limit=2) is None
    assert transcripts_in_window("No Such Group", None, None, limit=10) == []


def _group_with_owner(db_session, make_user, make_group):
    owner = make_user(username="owner")
    group = make_group(name="Team A", owner=owner)
    return owner, group


def test_conversation_retrieve_only_returns_window_without_llm(
    client, db_session, make_user, make_group, auth_header_for, monkeypatch
):
    from backend.project_rag import group_service

    owner, group = _group_with_owner(db_session, make_user, make_group)
    seen = {}

    def fake_window(group_name, since, until, limit):
        seen.update(group_name=group_name, since=since, until=until)
        return [_chunk(2, "2026-09-08", 0, "first")]

    monkeypatch.setattr(group_service, "transcripts_in_window", fake_window)
    monkeypatch.setattr(
        group_service, "OllamaClient", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM called"))
    )

    response = client.post(
        f"/groups/{group.id}/conversation/query",
        json={"question": "meetings", "since": "2026-09-07", "until": "2026-09-14", "retrieve_only": True},
        headers=auth_header_for(owner.id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "" and body["model"] is None
    assert body["complete_window"] is True
    assert body["evidence"][0]["text"] == "first"
    assert body["evidence"][0]["metadata"]["meeting_date"] == "2026-09-08"
    assert seen == {"group_name": "Team A", "since": date(2026, 9, 7), "until": date(2026, 9, 14)}


def test_conversation_window_over_limit_falls_back_to_ranked_search(
    client, db_session, make_user, make_group, auth_header_for, monkeypatch
):
    from backend.project_rag import group_service

    owner, group = _group_with_owner(db_session, make_user, make_group)
    monkeypatch.setattr(group_service, "transcripts_in_window", lambda *a, **k: None)
    calls = {}

    def fake_search(group_name, query, n_results, since, until):
        calls.update(since=since, until=until)
        return [{**_chunk(2, "2026-09-08", 0, "ranked"), "distance": 0.1}]

    monkeypatch.setattr(group_service, "search_transcripts", fake_search)

    response = client.post(
        f"/groups/{group.id}/conversation/query",
        json={"question": "meetings", "since": "2026-09-07", "retrieve_only": True},
        headers=auth_header_for(owner.id),
    )

    assert response.status_code == 200
    assert response.json()["complete_window"] is False
    assert calls == {"since": date(2026, 9, 7), "until": None}
