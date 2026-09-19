from app.mail.fake_client import FakeMailClient, make_test_email


def test_fetch_new_messages_excludes_processed():
    msg = make_test_email("alice@uni.ac.uk")
    client = FakeMailClient([msg])

    assert client.fetch_new_messages() == [msg]
    client.mark_processed(msg.provider_ref)
    assert client.fetch_new_messages() == []


def test_fetch_new_messages_respects_limit():
    msgs = [make_test_email("alice@uni.ac.uk", message_id=f"<m{i}@fake>") for i in range(5)]
    client = FakeMailClient(msgs)
    assert len(client.fetch_new_messages(limit=2)) == 2


def test_send_email_is_recorded_and_returns_an_id():
    client = FakeMailClient()
    sent_id = client.send_email(to="alice@uni.ac.uk", subject="Hi", body_text="Body")
    assert sent_id
    assert len(client.sent) == 1
    assert client.sent[0].to == "alice@uni.ac.uk"
    assert client.sent[0].subject == "Hi"
