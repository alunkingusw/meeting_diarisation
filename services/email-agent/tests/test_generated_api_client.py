from app.diarisation.generated_client.fast_api_client.models.meeting_comment_create import (
    MeetingCommentCreate,
)


def test_generated_comment_model_matches_manager_contract():
    payload = MeetingCommentCreate(comment="Discuss the deadline.")

    assert payload.to_dict() == {"comment": "Discuss the deadline."}