from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import SAFE_METHODS, AllowAny, IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView

from ..dashboard import calcular_metricas, normalizar_periodo
from ..models import Loja, Pedido, Produto, SubPedido, loja_do_usuario
from .permissions import EhDonoDoProdutoOuSomenteLeitura, EhLojistaOuAdmin
from .serializers import (
    AdicionarItemSerializer,
    CupomCodigoSerializer,
    LojaSerializer,
    PedidoSerializer,
    ProdutoSerializer,
    SubPedidoSerializer,
    SubPedidoStatusSerializer,
)


def _erro_de_negocio(exc: DjangoValidationError):
    """Converte erros de regra de negócio do model em HTTP 400 da API."""
    return ValidationError({"detail": exc.messages})


class LojaViewSet(viewsets.ReadOnlyModelViewSet):
    """Vitrine pública das lojas (vendedores) ativas do marketplace."""

    serializer_class = LojaSerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"
    search_fields = ["nome", "descricao"]
    ordering_fields = ["nome", "criada_em"]

    def get_queryset(self):
        return Loja.objects.filter(ativa=True).annotate(total_produtos=Count("produtos")).order_by("nome")

    @extend_schema(responses=ProdutoSerializer(many=True))
    @action(detail=True, methods=["get"])
    def produtos(self, request, slug=None):
        """Lista os produtos de uma loja."""
        loja = self.get_object()
        qs = loja.produtos.select_related("loja").prefetch_related("saldos").order_by("nome")
        pagina = self.paginate_queryset(qs)
        serializer = ProdutoSerializer(pagina, many=True, context=self.get_serializer_context())
        return self.get_paginated_response(serializer.data)


@extend_schema(parameters=[
    OpenApiParameter("categoria", str, description="Filtra pela categoria (ex: audio, cabos)"),
    OpenApiParameter("loja", str, description="Slug da loja, ou 'oficial' para produtos sem loja"),
    OpenApiParameter("minhas", bool, description="1 = somente produtos da minha loja (lojista)"),
    OpenApiParameter("preco_min", float), OpenApiParameter("preco_max", float),
])
class ProdutoViewSet(viewsets.ModelViewSet):
    """
    Catálogo do marketplace.
    Leitura pública; lojistas cadastram/alteram apenas os próprios produtos; administradores tudo.
    """

    serializer_class = ProdutoSerializer
    permission_classes = [EhDonoDoProdutoOuSomenteLeitura]
    search_fields = ["nome", "codigo_sku", "loja__nome"]
    ordering_fields = ["nome", "preco_venda", "codigo_sku"]
    ordering = ["nome"]

    def get_queryset(self):
        qs = Produto.objects.select_related("loja", "fornecedor_padrao").prefetch_related("saldos")
        user = self.request.user
        if self.request.method in SAFE_METHODS and not user.is_staff:
            qs = qs.disponiveis()

        params = self.request.query_params
        if params.get("categoria"):
            qs = qs.filter(categoria=params["categoria"])
        if params.get("loja") == "oficial":
            qs = qs.filter(loja__isnull=True)
        elif params.get("loja"):
            qs = qs.filter(loja__slug=params["loja"])
        if params.get("minhas") in ("1", "true", "True"):
            qs = qs.filter(loja=loja_do_usuario(user)) if loja_do_usuario(user) else qs.none()
        try:
            if params.get("preco_min"):
                qs = qs.filter(preco_venda__gte=params["preco_min"])
            if params.get("preco_max"):
                qs = qs.filter(preco_venda__lte=params["preco_max"])
        except (ValueError, DjangoValidationError):
            raise ValidationError({"detail": "preco_min/preco_max devem ser números."})
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        if user.is_staff:
            serializer.save()  # administrador pode escolher a loja (ou deixar como loja oficial)
        else:
            serializer.save(loja=loja_do_usuario(user))  # lojista: sempre a própria loja

    def perform_update(self, serializer):
        if self.request.user.is_staff:
            serializer.save()
        else:
            serializer.save(loja=serializer.instance.loja)  # lojista não pode transferir produto

    def perform_destroy(self, instance):
        if instance.itens_pedido.filter(pedido__status="finalizado").exists():
            raise ValidationError({"detail": "Produto possui vendas finalizadas e não pode ser excluído."})
        instance.delete()


class PedidoViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                    mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """
    Pedidos (carrinho) do cliente autenticado. Administradores veem todos.
    Fluxo: POST /pedidos/ → POST /pedidos/{id}/itens/ → POST /pedidos/{id}/aplicar-cupom/ → POST /pedidos/{id}/finalizar/
    """

    serializer_class = PedidoSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    ordering_fields = ["criado_em", "finalizado_em"]
    search_fields = ["itens__produto__nome"]

    def get_queryset(self):
        qs = Pedido.objects.select_related("cliente", "vendedor", "cupom").prefetch_related(
            "itens__produto__loja", "subpedidos__loja"
        ).order_by("-criado_em")
        if self.request.user.is_authenticated and not self.request.user.is_staff:
            qs = qs.filter(cliente=self.request.user)
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs

    def perform_create(self, serializer):
        serializer.save(cliente=self.request.user)

    def perform_destroy(self, instance):
        if instance.status != "carrinho":
            raise ValidationError({"detail": "Apenas pedidos em aberto (carrinho) podem ser excluídos."})
        instance.delete()

    def _resposta(self, pedido, codigo=status.HTTP_200_OK):
        pedido = self.get_queryset().get(pk=pedido.pk)  # recarrega com prefetch atualizado
        return Response(PedidoSerializer(pedido, context=self.get_serializer_context()).data, status=codigo)

    @extend_schema(request=AdicionarItemSerializer, responses=PedidoSerializer)
    @action(detail=True, methods=["post"], url_path="itens")
    def adicionar_item(self, request, pk=None):
        pedido = self.get_object()
        entrada = AdicionarItemSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            pedido.adicionar_item(entrada.validated_data["produto"], entrada.validated_data["quantidade"])
        except DjangoValidationError as e:
            raise _erro_de_negocio(e)
        return self._resposta(pedido, status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=PedidoSerializer)
    @action(detail=True, methods=["delete"], url_path=r"itens/(?P<item_id>\d+)")
    def remover_item(self, request, pk=None, item_id=None):
        pedido = self.get_object()
        if pedido.status != "carrinho":
            raise ValidationError({"detail": "Este pedido já foi finalizado ou cancelado."})
        item = get_object_or_404(pedido.itens, pk=item_id)
        item.delete()
        return self._resposta(pedido)

    @extend_schema(request=CupomCodigoSerializer, responses=PedidoSerializer)
    @action(detail=True, methods=["post"], url_path="aplicar-cupom")
    def aplicar_cupom(self, request, pk=None):
        pedido = self.get_object()
        entrada = CupomCodigoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            pedido.aplicar_cupom(entrada.validated_data["codigo"])
        except DjangoValidationError as e:
            raise _erro_de_negocio(e)
        return self._resposta(pedido)

    @extend_schema(request=None, responses=PedidoSerializer)
    @action(detail=True, methods=["post"])
    def finalizar(self, request, pk=None):
        """Finaliza o pedido e o divide em sub-pedidos (um por loja)."""
        pedido = self.get_object()
        try:
            pedido.finalizar()
        except DjangoValidationError as e:
            raise _erro_de_negocio(e)
        return self._resposta(pedido)


class SubPedidoViewSet(viewsets.ReadOnlyModelViewSet):
    """Sub-pedidos: a parte de cada pedido que cabe a uma loja. O lojista vê apenas os da sua loja."""

    serializer_class = SubPedidoSerializer
    ordering_fields = ["criado_em", "valor_bruto"]

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [AllowAny()]
        return [IsAuthenticated(), EhLojistaOuAdmin()]

    def get_queryset(self):
        qs = SubPedido.objects.select_related("loja", "pedido__cliente").order_by("-criado_em")
        user = self.request.user
        if user.is_authenticated and not user.is_staff:
            loja = loja_do_usuario(user)
            qs = qs.filter(loja=loja) if loja else qs.none()
        elif self.request.query_params.get("loja"):
            qs = qs.filter(loja__slug=self.request.query_params["loja"])
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs

    @extend_schema(request=SubPedidoStatusSerializer, responses=SubPedidoSerializer)
    @action(detail=True, methods=["patch", "post"], url_path="status")
    def alterar_status(self, request, pk=None):
        """Avança o status de entrega: pendente → enviado → entregue (ou pendente → cancelado)."""
        subpedido = self.get_object()
        entrada = SubPedidoStatusSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            subpedido.alterar_status(entrada.validated_data["status"])
        except DjangoValidationError as e:
            raise _erro_de_negocio(e)
        return Response(self.get_serializer(subpedido).data)


class DashboardAPIView(APIView):
    """
    Métricas de vendas (KPIs, série diária, ranking de lojas, top produtos...).
    Administrador ou visitante: marketplace inteiro (ou ?loja=<slug>). Lojista logado: somente a própria loja.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[
            OpenApiParameter("dias", int, description="Período em dias: 7, 30, 90 ou 365 (padrão 30)"),
            OpenApiParameter("loja", str, description="Slug da loja (administradores ou consulta pública)"),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        dias = normalizar_periodo(request.query_params.get("dias"))
        if not request.user.is_authenticated or request.user.is_staff:
            slug = request.query_params.get("loja")
            loja = get_object_or_404(Loja, slug=slug) if slug else None
        else:
            loja = loja_do_usuario(request.user)
            if loja is None:
                raise PermissionDenied("Apenas lojistas ou administradores possuem dashboard de vendas.")
        return Response(calcular_metricas(loja=loja, dias=dias))
