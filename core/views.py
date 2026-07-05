from rest_framework import generics, permissions, viewsets
from rest_framework_simplejwt.views import TokenObtainPairView
from .models import Project, Conversation
from .serializers import (
    RegisterSerializer,
    ProfileSerializer,
    EmailOrUsernameTokenSerializer,
    ProjectSerializer,
    ConversationSerializer
)


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
        # TODO: DON'T delete the row. Set instance.status to "deleted", then instance.save()
        Conversation.objects.update(id=instance.id, user=self.request.user, status= 'deleted')