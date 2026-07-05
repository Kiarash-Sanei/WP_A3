from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import RegisterView, LoginView, ProfileView, ProjectViewSet

router = DefaultRouter()
router.register("projects", ProjectViewSet, basename="project")
urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/profile/", ProfileView.as_view(), name="profile"),
] + router.urls