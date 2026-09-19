def test_openapi_exposes_email_agent_contract(client):
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]

    assert "/admin/user-token" in paths
    assert "post" in paths["/admin/user-token"]
    assert "/groups/{group_id}" in paths
    assert "/groups/{group_id}/meetings/" in paths
    assert "/groups/{group_id}/meetings/{meeting_id}/comments" in paths
    assert "/groups/{group_id}/transcripts/search" in paths


def test_openapi_describes_comment_request_and_response(client):
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/groups/{group_id}/meetings/{meeting_id}/comments"]["post"]

    request_schema = operation["requestBody"]["content"]["application/json"]["schema"]
    response_schema = operation["responses"]["201"]["content"]["application/json"]["schema"]

    assert request_schema["$ref"] == "#/components/schemas/MeetingCommentCreate"
    assert response_schema["$ref"] == "#/components/schemas/MeetingCommentOut"
