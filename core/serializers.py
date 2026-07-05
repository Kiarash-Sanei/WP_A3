from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import Project, Conversation, Assistant, AIModel, Message, Attachment

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ("id", "username", "email", "password", "first_name", "last_name")

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)   # hashes the password; never store it raw
        user.save()
        return user


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "id", "username", "email",
            "first_name", "last_name", "subscription_type",
        )
        # username can't be changed here; subscription_type only changes via purchase
        read_only_fields = ("id", "username", "subscription_type")


class EmailOrUsernameTokenSerializer(TokenObtainPairSerializer):
    """Allow login with either username OR email in the same field."""

    def validate(self, attrs):
        login = attrs.get(self.username_field)
        if login and "@" in login:
            match = User.objects.filter(email__iexact=login).first()
            if match:
                attrs[self.username_field] = match.get_username()
        return super().validate(attrs)
    
class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        ordering = ["-created_at"]
        fields = ("id", "title", "description", "created_at")
        read_only_fields = ("id", "created_at")

class ConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        ordering = ["-created_at"]
        fields = ("id", "title", "status", "project", "ai_model", "assistant", "created_at")
        read_only_fields = ("id", "created_at")

class AssistantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Assistant
        ordering = ["-created_at"]
        fields = ("id", "title", "description", "system_prompt", "created_at")
        read_only_fields = ("id", "created_at")

class AIModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIModel
        fields = ("id", "name", "provider", "is_active")
        read_only_fields = ("id",)

class MessageSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True, required=False)
    class Meta:
        model = Message
        fields = ("id", "role", "content", "created_at", "file")
        read_only_fields = ("id", "role", "created_at")

class AttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attachment
        ordering = ["id"]
        fields = ("id", "file", "file_format", "size", "uploaded_at")
        read_only_fields = ("id", "file_format", "size", "uploaded_at")