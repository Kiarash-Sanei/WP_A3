from rest_framework.throttling import UserRateThrottle


class DailyMessageThrottle(UserRateThrottle):
    scope = "daily_messages"

    def allow_request(self, request, view):
        if request.user.is_authenticated and request.user.subscription_type == "premium":
            return True
        return super().allow_request(request, view)