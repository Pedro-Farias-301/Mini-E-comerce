from rest_framework import serializers

from ..models import ItemPedido, Loja, Pedido, Produto, SubPedido, Vendedor, loja_do_usuario


class LojaResumoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Loja
        fields = ["id", "nome", "slug"]


class LojaSerializer(serializers.ModelSerializer):
    total_produtos = serializers.IntegerField(read_only=True)

    class Meta:
        model = Loja
        fields = ["id", "nome", "slug", "descricao", "email_contato", "comissao_percentual", "total_produtos", "criada_em"]


class ProdutoSerializer(serializers.ModelSerializer):
    loja = LojaResumoSerializer(read_only=True)
    loja_id = serializers.PrimaryKeyRelatedField(
        source="loja", queryset=Loja.objects.all(), write_only=True, required=False, allow_null=True,
        help_text="Somente administradores podem escolher a loja. Para lojistas, a loja é sempre a do usuário logado.",
    )
    categoria_display = serializers.CharField(source="get_categoria_display", read_only=True)
    estoque_total = serializers.SerializerMethodField()

    class Meta:
        model = Produto
        fields = [
            "id", "codigo_sku", "nome", "categoria", "categoria_display", "preco_custo", "preco_venda",
            "ponto_de_pedido", "fornecedor_padrao", "loja", "loja_id", "estoque_total",
        ]

    def get_estoque_total(self, obj) -> int:
        return obj.total_em_estoque_geral()

    def validate_preco_venda(self, valor):
        if valor <= 0:
            raise serializers.ValidationError("O preço de venda deve ser maior que zero.")
        return valor

    def validate_preco_custo(self, valor):
        if valor <= 0:
            raise serializers.ValidationError("O preço de custo deve ser maior que zero.")
        return valor

    def validate(self, attrs):
        custo = attrs.get("preco_custo", getattr(self.instance, "preco_custo", None))
        venda = attrs.get("preco_venda", getattr(self.instance, "preco_venda", None))
        if custo is not None and venda is not None and venda < custo:
            raise serializers.ValidationError({"preco_venda": "O preço de venda não pode ser menor que o preço de custo."})
        return attrs

    def to_representation(self, instance):
        """O preço de custo é informação interna: só aparece para o dono do produto ou administradores."""
        data = super().to_representation(instance)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        loja = loja_do_usuario(user)
        eh_dono = loja is not None and instance.loja_id == loja.pk
        if not (user and user.is_authenticated and (user.is_staff or eh_dono)):
            data.pop("preco_custo", None)
        return data


class ItemPedidoSerializer(serializers.ModelSerializer):
    produto_nome = serializers.CharField(source="produto.nome", read_only=True)
    loja = serializers.CharField(source="produto.loja_nome", read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = ItemPedido
        fields = ["id", "produto", "produto_nome", "loja", "quantidade", "preco_unitario", "subtotal"]
        read_only_fields = ["produto", "quantidade", "preco_unitario"]


class SubPedidoResumoSerializer(serializers.ModelSerializer):
    loja = LojaResumoSerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = SubPedido
        fields = ["id", "loja", "status", "status_display", "valor_bruto", "valor_desconto", "valor_comissao", "valor_liquido"]


class PedidoSerializer(serializers.ModelSerializer):
    cliente = serializers.CharField(source="cliente.username", read_only=True, default=None)
    vendedor = serializers.PrimaryKeyRelatedField(queryset=Vendedor.objects.filter(ativo=True), required=False, allow_null=True)
    cupom = serializers.CharField(source="cupom.codigo", read_only=True, default=None)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    itens = ItemPedidoSerializer(many=True, read_only=True)
    subpedidos = SubPedidoResumoSerializer(many=True, read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    valor_desconto = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Pedido
        fields = [
            "id", "cliente", "vendedor", "cupom", "status", "status_display", "itens",
            "subtotal", "valor_desconto", "total", "subpedidos", "criado_em", "finalizado_em",
        ]
        read_only_fields = ["status", "criado_em", "finalizado_em"]


class SubPedidoSerializer(serializers.ModelSerializer):
    loja = LojaResumoSerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    proximos_status = serializers.SerializerMethodField()
    cliente = serializers.CharField(source="pedido.cliente.username", read_only=True, default=None)
    finalizado_em = serializers.DateTimeField(source="pedido.finalizado_em", read_only=True)
    itens = ItemPedidoSerializer(many=True, read_only=True)

    class Meta:
        model = SubPedido
        fields = [
            "id", "pedido", "cliente", "loja", "status", "status_display", "proximos_status", "itens",
            "valor_bruto", "valor_desconto", "taxa_comissao", "valor_comissao", "valor_liquido",
            "finalizado_em", "atualizado_em",
        ]

    def get_proximos_status(self, obj) -> list[str]:
        return [s for s, _ in obj.proximos_status]


# ─── Serializers de entrada para as ações customizadas ───────────────

class AdicionarItemSerializer(serializers.Serializer):
    produto = serializers.PrimaryKeyRelatedField(queryset=Produto.objects.disponiveis())
    quantidade = serializers.IntegerField(min_value=1, default=1)


class CupomCodigoSerializer(serializers.Serializer):
    codigo = serializers.CharField(max_length=30)


class SubPedidoStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=SubPedido.STATUS_CHOICES)
