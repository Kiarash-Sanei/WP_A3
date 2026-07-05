from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from core.models import AIModel, Conversation, Assistant, Project, Message
from core.throttling import DailyMessageThrottle

User = get_user_model()
PWD = "S3cure!pass9"


class BaseTest(APITestCase):
    def setUp(self):
        cache.clear()  # reset throttle counters between tests
        self.model = AIModel.objects.create(name="GPT-4", provider="OpenAI")

    def register(self, username, password=PWD):
        return self.client.post(
            "/api/auth/register/",
            {"username": username, "email": username + "@t.com", "password": password},
            format="json",
        )

    def get_token(self, login, password=PWD):
        return self.client.post(
            "/api/auth/login/", {"username": login, "password": password}, format="json"
        )

    def login_as(self, username):
        self.register(username)
        token = self.get_token(username).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + token)

    def new_conversation(self, title="c", project=None):
        body = {"title": title, "ai_model": self.model.id}
        if project is not None:
            body["project"] = project
        return self.client.post("/api/conversations/", body, format="json").data["id"]


# ---------- Auth / registration / login / profile ----------
class AuthTests(BaseTest):
    def test_register_returns_201(self):
        self.assertEqual(self.register("kia").status_code, 201)

    def test_register_never_returns_password(self):
        self.assertNotIn("password", self.register("kia").data)

    def test_register_rejects_weak_password(self):
        self.assertEqual(self.register("kia", password="123").status_code, 400)

    def test_register_rejects_duplicate_username(self):
        self.register("dup")
        self.assertEqual(self.register("dup").status_code, 400)

    def test_login_with_username(self):
        self.register("kia")
        self.assertIn("access", self.get_token("kia").data)

    def test_login_with_email(self):
        self.register("kia")
        self.assertIn("access", self.get_token("kia@t.com").data)

    def test_login_wrong_password_fails(self):
        self.register("kia")
        self.assertEqual(self.get_token("kia", password="wrong").status_code, 401)

    def test_profile_requires_auth(self):
        self.assertEqual(self.client.get("/api/auth/profile/").status_code, 401)

    def test_profile_returns_own_data(self):
        self.login_as("kia")
        self.assertEqual(self.client.get("/api/auth/profile/").data["username"], "kia")

    def test_profile_patch_updates_name(self):
        self.login_as("kia")
        r = self.client.patch("/api/auth/profile/", {"last_name": "Sanei"}, format="json")
        self.assertEqual(r.data["last_name"], "Sanei")

    def test_profile_subscription_type_is_read_only(self):
        self.login_as("kia")
        self.client.patch("/api/auth/profile/", {"subscription_type": "premium"}, format="json")
        self.assertEqual(self.client.get("/api/auth/profile/").data["subscription_type"], "free")


# ---------- Projects ----------
class ProjectTests(BaseTest):
    def test_create_sets_owner(self):
        self.login_as("alice")
        self.assertEqual(self.client.post("/api/projects/", {"title": "p"}, format="json").status_code, 201)

    def test_list_only_own(self):
        self.login_as("alice")
        self.client.post("/api/projects/", {"title": "p"}, format="json")
        self.login_as("bob")
        self.assertEqual(self.client.get("/api/projects/").data["count"], 0)

    def test_cannot_retrieve_others(self):
        self.login_as("alice")
        pid = self.client.post("/api/projects/", {"title": "p"}, format="json").data["id"]
        self.login_as("bob")
        self.assertEqual(self.client.get(f"/api/projects/{pid}/").status_code, 404)

    def test_delete_cascades_conversations(self):
        self.login_as("alice")
        pid = self.client.post("/api/projects/", {"title": "p"}, format="json").data["id"]
        cid = self.new_conversation(project=pid)
        self.client.delete(f"/api/projects/{pid}/")
        self.assertFalse(Conversation.objects.filter(id=cid).exists())

    def test_project_conversations_lists_only_that_project(self):
        self.login_as("alice")
        pid = self.client.post("/api/projects/", {"title": "A"}, format="json").data["id"]
        self.new_conversation(project=pid)
        self.new_conversation()  # no project
        self.assertEqual(self.client.get(f"/api/projects/{pid}/conversations/").data["count"], 1)

    def test_project_conversations_blocked_for_others(self):
        self.login_as("alice")
        pid = self.client.post("/api/projects/", {"title": "A"}, format="json").data["id"]
        self.login_as("bob")
        self.assertEqual(self.client.get(f"/api/projects/{pid}/conversations/").status_code, 404)


# ---------- Conversations ----------
class ConversationTests(BaseTest):
    def test_create_sets_user(self):
        self.login_as("u")
        self.assertTrue(self.new_conversation())

    def test_delete_is_soft(self):
        self.login_as("u")
        cid = self.new_conversation()
        self.assertEqual(self.client.delete(f"/api/conversations/{cid}/").status_code, 204)
        self.assertEqual(Conversation.objects.get(id=cid).status, "deleted")

    def test_soft_deleted_hidden_from_list(self):
        self.login_as("u")
        cid = self.new_conversation()
        self.client.delete(f"/api/conversations/{cid}/")
        self.assertEqual(self.client.get("/api/conversations/").data["count"], 0)

    def test_cannot_access_others(self):
        self.login_as("alice")
        cid = self.new_conversation()
        self.login_as("bob")
        self.assertEqual(self.client.get(f"/api/conversations/{cid}/").status_code, 404)

    def test_patch_title(self):
        self.login_as("u")
        cid = self.new_conversation()
        r = self.client.patch(f"/api/conversations/{cid}/", {"title": "renamed"}, format="json")
        self.assertEqual(r.data["title"], "renamed")


# ---------- Messages ----------
class MessageTests(BaseTest):
    def test_send_creates_user_and_assistant_messages(self):
        self.login_as("u")
        cid = self.new_conversation()
        self.client.post(f"/api/conversations/{cid}/messages/", {"content": "hi"}, format="json")
        self.assertEqual(Message.objects.filter(conversation_id=cid).count(), 2)

    def test_reply_is_assistant_and_names_model(self):
        self.login_as("u")
        cid = self.new_conversation()
        r = self.client.post(f"/api/conversations/{cid}/messages/", {"content": "hi"}, format="json")
        self.assertEqual(r.data["role"], "assistant")
        self.assertIn("GPT-4", r.data["content"])

    def test_history_is_paginated(self):
        self.login_as("u")
        cid = self.new_conversation()
        for i in range(11):
            self.client.post(f"/api/conversations/{cid}/messages/", {"content": f"m{i}"}, format="json")
        data = self.client.get(f"/api/conversations/{cid}/messages/").data
        self.assertEqual(data["count"], 22)
        self.assertEqual(len(data["results"]), 20)

    def test_cannot_post_to_others_conversation(self):
        self.login_as("alice")
        cid = self.new_conversation()
        self.login_as("bob")
        r = self.client.post(f"/api/conversations/{cid}/messages/", {"content": "x"}, format="json")
        self.assertEqual(r.status_code, 404)

    def test_message_with_file_creates_attachment(self):
        self.login_as("u")
        cid = self.new_conversation()
        f = SimpleUploadedFile("n.txt", b"data", content_type="text/plain")
        self.client.post(f"/api/conversations/{cid}/messages/", {"content": "see", "file": f}, format="multipart")
        umsg = Message.objects.filter(conversation_id=cid, role="user").first()
        self.assertEqual(self.client.get(f"/api/messages/{umsg.id}/attachments/").data["count"], 1)

    def test_cannot_download_others_attachments(self):
        self.login_as("alice")
        cid = self.new_conversation()
        f = SimpleUploadedFile("n.txt", b"data", content_type="text/plain")
        self.client.post(f"/api/conversations/{cid}/messages/", {"content": "see", "file": f}, format="multipart")
        umsg = Message.objects.filter(conversation_id=cid, role="user").first()
        self.login_as("bob")
        self.assertEqual(self.client.get(f"/api/messages/{umsg.id}/attachments/").status_code, 404)


# ---------- Assistants ----------
class AssistantTests(BaseTest):
    def test_public_visible_to_everyone(self):
        Assistant.objects.create(title="Public", system_prompt="x")
        self.login_as("u")
        titles = [a["title"] for a in self.client.get("/api/assistants/").data["results"]]
        self.assertIn("Public", titles)

    def test_private_hidden_from_others(self):
        self.login_as("alice")
        self.client.post("/api/assistants/", {"title": "Mine", "system_prompt": "x"}, format="json")
        self.login_as("bob")
        titles = [a["title"] for a in self.client.get("/api/assistants/").data["results"]]
        self.assertNotIn("Mine", titles)

    def test_cannot_edit_public(self):
        Assistant.objects.create(title="Public", system_prompt="x")
        self.login_as("u")
        pid = [a for a in self.client.get("/api/assistants/").data["results"] if a["title"] == "Public"][0]["id"]
        self.assertEqual(self.client.patch(f"/api/assistants/{pid}/", {"title": "h"}, format="json").status_code, 403)

    def test_can_edit_own(self):
        self.login_as("u")
        pid = self.client.post("/api/assistants/", {"title": "Mine", "system_prompt": "x"}, format="json").data["id"]
        self.assertEqual(self.client.patch(f"/api/assistants/{pid}/", {"title": "New"}, format="json").status_code, 200)


# ---------- AI models (read-only for users) ----------
class AIModelTests(BaseTest):
    def test_user_can_list(self):
        self.login_as("u")
        self.assertEqual(self.client.get("/api/models/").status_code, 200)

    def test_user_cannot_create(self):
        self.login_as("u")
        self.assertEqual(self.client.post("/api/models/", {"name": "X", "provider": "Y"}, format="json").status_code, 403)

    def test_superuser_can_create(self):
        User.objects.create_superuser("boss", "boss@t.com", PWD)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + self.get_token("boss").data["access"])
        self.assertEqual(self.client.post("/api/models/", {"name": "Claude", "provider": "Anthropic"}, format="json").status_code, 201)


# ---------- Subscription ----------
class SubscriptionTests(BaseTest):
    def test_status_free_shows_remaining(self):
        self.login_as("u")
        self.assertEqual(self.client.get("/api/subscription/status/").data["remaining"], 50)

    def test_remaining_decrements_after_message(self):
        self.login_as("u")
        cid = self.new_conversation()
        self.client.post(f"/api/conversations/{cid}/messages/", {"content": "hi"}, format="json")
        self.assertEqual(self.client.get("/api/subscription/status/").data["remaining"], 49)

    def test_plans_are_listed(self):
        self.login_as("u")
        self.assertEqual(len(self.client.get("/api/subscription/plans/").data), 2)

    def test_purchase_upgrades_to_premium(self):
        self.login_as("u")
        self.client.post("/api/subscription/purchase/", {"plan_id": "premium_monthly"}, format="json")
        self.assertEqual(self.client.get("/api/subscription/status/").data["subscription_type"], "premium")

    def test_purchase_rejects_bad_plan(self):
        self.login_as("u")
        self.assertEqual(self.client.post("/api/subscription/purchase/", {"plan_id": "nope"}, format="json").status_code, 400)


# ---------- Throttling ----------
class ThrottleTests(BaseTest):
    def setUp(self):
        super().setUp()
        DailyMessageThrottle.THROTTLE_RATES = {"daily_messages": "2/day"}

    def tearDown(self):
        DailyMessageThrottle.THROTTLE_RATES = {"daily_messages": "50/day"}

    def test_free_user_blocked_after_limit(self):
        self.login_as("u")
        cid = self.new_conversation()
        codes = [self.client.post(f"/api/conversations/{cid}/messages/", {"content": "x"}, format="json").status_code for _ in range(3)]
        self.assertEqual(codes, [201, 201, 429])

    def test_premium_user_not_throttled(self):
        self.login_as("u")
        self.client.post("/api/subscription/purchase/", {"plan_id": "premium_monthly"}, format="json")
        cid = self.new_conversation()
        codes = [self.client.post(f"/api/conversations/{cid}/messages/", {"content": "x"}, format="json").status_code for _ in range(4)]
        self.assertTrue(all(c == 201 for c in codes))


# ---------- Account linking / switching ----------
class AccountLinkTests(BaseTest):
    def _link_bob_to_alice(self):
        self.register("bob")
        self.login_as("alice")
        return self.client.post("/api/auth/account-link/", {"username": "bob", "password": PWD}, format="json")

    def test_link_with_correct_password(self):
        self.assertEqual(self._link_bob_to_alice().status_code, 201)

    def test_link_with_wrong_password(self):
        self.register("bob")
        self.login_as("alice")
        self.assertEqual(self.client.post("/api/auth/account-link/", {"username": "bob", "password": "no"}, format="json").status_code, 400)

    def test_cannot_link_self(self):
        self.login_as("alice")
        self.assertEqual(self.client.post("/api/auth/account-link/", {"username": "alice", "password": PWD}, format="json").status_code, 400)

    def test_linked_accounts_listed(self):
        self._link_bob_to_alice()
        self.assertEqual(len(self.client.get("/api/auth/linked-accounts/").data), 1)

    def test_switch_changes_identity(self):
        self._link_bob_to_alice()
        bob_id = self.client.get("/api/auth/linked-accounts/").data[0]["id"]
        token = self.client.post("/api/auth/switch/", {"user_id": bob_id}, format="json").data["access"]
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
        self.assertEqual(self.client.get("/api/auth/profile/").data["username"], "bob")

    def test_switch_to_unlinked_fails(self):
        self.login_as("alice")
        self.assertEqual(self.client.post("/api/auth/switch/", {"user_id": 9999}, format="json").status_code, 400)