from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    class SubscriptionType(models.TextChoices):
        FREE = "free", "Free"
        PREMIUM = "premium", "Premium"

    email = models.EmailField(unique=True)
    subscription_type = models.CharField(
        max_length=10,
        choices=SubscriptionType.choices,
        default=SubscriptionType.FREE,
    )

    def __str__(self):
        return self.username


class Project(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="projects"
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class AIModel(models.Model):
    name = models.CharField(max_length=100)
    provider = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Assistant(models.Model):
    # owner == null  -->  public / system-default assistant
    # owner set      -->  private assistant, only this user may use/edit it
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assistants",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    system_prompt = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_public(self):
        return self.owner_id is None

    def __str__(self):
        return self.title


class Conversation(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"
        DELETED = "deleted", "Deleted"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations"
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="conversations",
        null=True,
        blank=True,
    )
    ai_model = models.ForeignKey(
        AIModel, on_delete=models.PROTECT, related_name="conversations"
    )
    assistant = models.ForeignKey(
        Assistant,
        on_delete=models.SET_NULL,
        related_name="conversations",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Message(models.Model):
    class Role(models.TextChoices):
        USER = "user", "User"
        SYSTEM = "system", "System"
        ASSISTANT = "assistant", "Assistant"

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role}: {self.content[:30]}"


class Attachment(models.Model):
    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name="attachments"
    )
    file = models.FileField(upload_to="attachments/")
    file_format = models.CharField(max_length=50, blank=True)
    size = models.PositiveIntegerField(default=0)  # bytes
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file.name