from rest_framework import generics, permissions, viewsets
from rest_framework_simplejwt.views import TokenObtainPairView
from .models import Project, Conversation, Assistant, AIModel, Message, Attachment
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

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class LoginView(TokenObtainPairView):
    serializer_class = EmailOrUsernameTokenSerializer
    permission_classes = [permissions.AllowAny]


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user
    
class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Project.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

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

class AssistantViewSet(viewsets.ModelViewSet):
    serializer_class = AssistantSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]

    def get_queryset(self):
        return Assistant.objects.filter(Q(owner__isnull=True) | Q(owner=self.request.user))

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

class AIModelViewSet(viewsets.ModelViewSet):
    queryset = AIModel.objects.all()
    serializer_class = AIModelSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrReadOnly]

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