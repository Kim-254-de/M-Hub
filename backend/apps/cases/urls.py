from rest_framework.routers import SimpleRouter

from .views import CaseViewSet

router = SimpleRouter()
router.register("cases", CaseViewSet, basename="case")

urlpatterns = router.urls
