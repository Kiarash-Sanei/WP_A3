from rest_framework import generics, permissions, viewsets
from drf_spectacular.utils import (
    extend_schema, extend_schema_view, OpenApiExample, inline_serializer,
)
from rest_framework import serializers as rf_serializers
from rest_framework_simplejwt.views import TokenObtainPairView
from .models import Project, Conversation, Assistant, AIModel, Message, Attachment, LinkedAccount
from .serializers import (
    RegisterSerializer,
    ProfileSerializer,
    EmailOrUsernameTokenSerializer,
    ProjectSerializer,
    ConversationSerializer,
    AssistantSerializer,
    AIModelSerializer,
    MessageSerializer,
    AttachmentSerializer,
)
from django.db.models import Q
from .permissions import IsOwnerOrReadOnly, IsAdminOrReadOnly
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from .services import generate_mock_reply
from rest_framework.views import APIView
from django.utils import timezone
from .throttling import DailyMessageThrottle
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken

@extend_schema(
    summary="Register a new user",
    examples=[OpenApiExample("Register", value={"username": "kia", "email": "kia@example.com", "password": "S3cure!pass9"}, request_only=True)],
)
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


@extend_schema(
    summary="Log in with username or email; returns JWT access + refresh tokens",
    examples=[
        OpenApiExample("Login", value={"username": "kia", "password": "S3cure!pass9"}, request_only=True),
        OpenApiExample("Tokens", value={"access": "<jwt-access>", "refresh": "<jwt-refresh>"}, response_only=True),
    ],
)
class LoginView(TokenObtainPairView):
    serializer_class = EmailOrUsernameTokenSerializer
    permission_classes = [permissions.AllowAny]


@extend_schema_view(
    get=extend_schema(summary="Get my profile",
        examples=[OpenApiExample("My profile", value={"id": 1, "username": "kia", "email": "kia@example.com", "first_name": "Kiarash", "last_name": "Sanei", "subscription_type": "free"}, response_only=True)]),
    put=extend_schema(exclude=True),
    patch=extend_schema(summary="Update my profile",
        examples=[OpenApiExample("Update name", value={"first_name": "Kiarash", "last_name": "Sanei"}, request_only=True)]),
)
class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user
    
@extend_schema_view(
    create=extend_schema(summary="Create a project",
        examples=[OpenApiExample("New project", value={"title": "University", "description": "coursework chats"}, request_only=True)]),
)
class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Project.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

@extend_schema_view(
    create=extend_schema(summary="Start a conversation (pick a model, optionally an assistant/project)",
        examples=[OpenApiExample("New conversation", value={"title": "My chat", "ai_model": 1, "assistant": None, "project": None}, request_only=True)]),
)
class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Conversation.objects.filter(user=self.request.user).exclude(status="deleted")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_destroy(self, instance):
        instance.status = "deleted"
        instance.save()

@extend_schema_view(
    create=extend_schema(summary="Create a custom assistant",
        examples=[OpenApiExample("New assistant", value={"title": "Translator", "description": "Translates to English", "system_prompt": "You are a translator."}, request_only=True)]),
)
class AssistantViewSet(viewsets.ModelViewSet):
    serializer_class = AssistantSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]

    def get_queryset(self):
        return Assistant.objects.filter(Q(owner__isnull=True) | Q(owner=self.request.user))

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

@extend_schema_view(
    create=extend_schema(summary="Add an AI model (superuser only)",
        examples=[OpenApiExample("New model", value={"name": "Claude-3", "provider": "Anthropic", "is_active": True}, request_only=True)]),
)
class AIModelViewSet(viewsets.ModelViewSet):
    queryset = AIModel.objects.all()
    serializer_class = AIModelSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrReadOnly]

@extend_schema_view(
    get=extend_schema(summary="Message history (paginated)"),
    post=extend_schema(
        summary="Send a message; get a mocked reply. Attach a file via multipart/form-data.",
        examples=[
            OpenApiExample("Send", value={"content": "Hello, world!"}, request_only=True),
            OpenApiExample("Mocked reply", value={"id": 2, "role": "assistant", "content": "[GPT-4]: I received your message: Hello, world!", "created_at": "2026-07-05T12:00:00Z"}, response_only=True),
        ],
    ),
)
class MessageListCreateView(generics.ListCreateAPIView):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_conversation(self):
        return get_object_or_404(Conversation, id=self.kwargs["conversation_id"], user=self.request.user)

    def get_queryset(self):
        return self.get_conversation().messages.all()

    def create(self, request, *args, **kwargs):
        conversation = self.get_conversation()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        content = serializer.validated_data["content"]

        user_msg = Message.objects.create(
            conversation=conversation, role=Message.Role.USER, content=content,
        )

        upload = serializer.validated_data.get("file")
        if upload:
            Attachment.objects.create(
                message=user_msg,
                file=upload,
                file_format=upload.content_type or "",
                size=upload.size,
            )

        reply = generate_mock_reply(conversation, content)
        assistant_msg = Message.objects.create(
            conversation=conversation, role=Message.Role.ASSISTANT, content=reply,
        )
        return Response(self.get_serializer(assistant_msg).data, status=201)
    
    def get_throttles(self):
        if self.request.method == "POST":
            return [DailyMessageThrottle()]
        return []
    
@extend_schema(
    summary="List/download attachments on a message",
    examples=[OpenApiExample("Attachments", value=[{"id": 1, "file": "/media/attachments/doc.pdf", "file_format": "application/pdf", "size": 20481, "uploaded_at": "2026-07-05T12:00:00Z"}], response_only=True)],
)
class AttachmentListView(generics.ListAPIView):
    serializer_class = AttachmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        message = get_object_or_404(
            Message,
            id=self.kwargs["message_id"],
            conversation__user=self.request.user,
        )
        return message.attachments.all()
    
FREE_DAILY_LIMIT = 50

SUBSCRIPTION_PLANS = [
    {"id": "premium_monthly", "name": "Premium Monthly", "price": 9.99},
    {"id": "premium_yearly", "name": "Premium Yearly", "price": 99.0},
]

@extend_schema(
    summary="Subscription status and remaining daily quota",
    responses=inline_serializer("SubscriptionStatusResponse", fields={
        "subscription_type": rf_serializers.CharField(),
        "daily_limit": rf_serializers.IntegerField(),
        "used": rf_serializers.IntegerField(),
        "remaining": rf_serializers.IntegerField(),
    }),
    examples=[OpenApiExample("Free user", value={"subscription_type": "free", "daily_limit": 50, "used": 3, "remaining": 47}, response_only=True)],
)
class SubscriptionStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.subscription_type == "premium":
            return Response({"subscription_type": "premium", "remaining": "unlimited"})
        today = timezone.now().date()
        used = Message.objects.filter(
            conversation__user=user,
            role=Message.Role.USER,
            created_at__date=today,
        ).count()
        return Response({"subscription_type": "free", "daily_limit": FREE_DAILY_LIMIT, "used": used, "remaining": FREE_DAILY_LIMIT - used})

@extend_schema(
    summary="List available subscription plans",
    responses=inline_serializer("PlanResponse", many=True, fields={
        "id": rf_serializers.CharField(),
        "name": rf_serializers.CharField(),
        "price": rf_serializers.FloatField(),
    }),
    examples=[OpenApiExample("Plans", value=[{"id": "premium_monthly", "name": "Premium Monthly", "price": 9.99}], response_only=True)],
)
class SubscriptionPlansView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(SUBSCRIPTION_PLANS)

@extend_schema(
    summary="Purchase a plan and upgrade to premium",
    request=inline_serializer("PurchaseRequest", fields={"plan_id": rf_serializers.CharField()}),
    responses=inline_serializer("PurchaseResponse", fields={"subscription_type": rf_serializers.CharField(), "plan": rf_serializers.CharField()}),
    examples=[
        OpenApiExample("Purchase", value={"plan_id": "premium_monthly"}, request_only=True),
        OpenApiExample("Upgraded", value={"subscription_type": "premium", "plan": "Premium Monthly"}, response_only=True),
    ],
)
class SubscriptionPurchaseView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
            plan_id = request.data.get("plan_id")
            plan = next((p for p in SUBSCRIPTION_PLANS if p["id"] == plan_id), None)
            if plan is None:
                return Response({"detail": "Invalid plan_id"}, status=400)
            request.user.subscription_type = "premium"
            request.user.save()
            return Response({"subscription_type": "premium", "plan": plan["name"]})
    
@extend_schema(
    summary="Link another account to yours",
    request=inline_serializer("AccountLinkRequest", fields={"username": rf_serializers.CharField(), "password": rf_serializers.CharField()}),
    responses=inline_serializer("AccountLinkResponse", fields={"detail": rf_serializers.CharField()}),
    examples=[OpenApiExample("Link", value={"username": "bob", "password": "S3cure!pass9"}, request_only=True)],
)
class AccountLinkView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request):
        target = authenticate(username=request.data.get("username"), password=request.data.get("password"))
        if target is None:
            return Response({"detail": "Invalid credentials"}, status=400)
        if target == request.user:
            return Response({"detail": "Cannot link your own account"}, status=400)
        LinkedAccount.objects.get_or_create(owner=request.user, linked_user=target)
        return Response({"detail": f"Linked {target.username}"}, status=201)


@extend_schema(
    summary="List accounts linked to you",
    responses=inline_serializer("LinkedAccountsResponse", many=True, fields={"id": rf_serializers.IntegerField(), "username": rf_serializers.CharField()}),
    examples=[OpenApiExample("Linked", value=[{"id": 2, "username": "bob"}], response_only=True)],
)
class LinkedAccountsView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        links = request.user.linked_accounts.all()
        return Response([{"id": l.linked_user.id, "username": l.linked_user.username} for l in links])


@extend_schema(
    summary="Switch to a linked account (returns new JWT tokens)",
    request=inline_serializer("SwitchRequest", fields={"user_id": rf_serializers.IntegerField()}),
    responses=inline_serializer("SwitchResponse", fields={"access": rf_serializers.CharField(), "refresh": rf_serializers.CharField()}),
    examples=[OpenApiExample("Switch", value={"user_id": 2}, request_only=True)],
)
class AccountSwitchView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request):
        link = request.user.linked_accounts.filter(linked_user_id=request.data.get("user_id")).first()
        if link is None:
            return Response({"detail": "Account not linked"}, status=400)
        refresh = RefreshToken.for_user(link.linked_user)
        return Response({"access": str(refresh.access_token), "refresh": str(refresh)})
    
@extend_schema(summary="List conversations inside a project")
class ProjectConversationsView(generics.ListAPIView):
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        project = get_object_or_404(Project, id=self.kwargs["project_id"], owner=self.request.user)
        return project.conversations.exclude(status="deleted")