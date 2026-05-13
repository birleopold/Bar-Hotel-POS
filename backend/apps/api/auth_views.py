from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


class TokenObtainPairThrottledView(TokenObtainPairView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "jwt_obtain"


class TokenRefreshThrottledView(TokenRefreshView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "jwt_refresh"
