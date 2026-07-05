from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import RegisterView, LoginView, ProfileView, ProjectViewSet, ConversationViewSet, AssistantViewSet, AIModelViewSet, MessageListCreateView, AttachmentListView

router = DefaultRouter()
router.register("projects", ProjectViewSet, basename="project")
router.register("conversations", ConversationViewSet, basename="conversation")
router.register("assistants", AssistantViewSet, basename="assistant")
router.register("models", AIModelViewSet, basename="aimodel")
urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/profile/", ProfileView.as_view(), name="profile"),
    path("conversations/<int:conversation_id>/messages/", MessageListCreateView.as_view(), name="messages"),
    path("messages/<int:message_id>/attachments/", AttachmentListView.as_view(), name="attachments"),
] + router.urls