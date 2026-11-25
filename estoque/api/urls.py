from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from .views import DashboardAPIView, LojaViewSet, PedidoViewSet, ProdutoViewSet, SubPedidoViewSet

router = DefaultRouter()
router.register("lojas", LojaViewSet, basename="loja")
router.register("produtos", ProdutoViewSet, basename="produto")
router.register("pedidos", PedidoViewSet, basename="pedido")
router.register("subpedidos", SubPedidoViewSet, basename="subpedido")

urlpatterns = [
    path("dashboard/", DashboardAPIView.as_view(), name="api-dashboard"),
    path("token/", obtain_auth_token, name="api-token"),
    path("", include(router.urls)),
]
