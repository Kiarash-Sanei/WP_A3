def generate_mock_reply(conversation, user_text):
    return f"[{conversation.ai_model.name}]: I received your message: {user_text}"