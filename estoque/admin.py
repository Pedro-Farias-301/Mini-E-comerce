from django.contrib import admin
from .models import Fornecedor, Deposito, Produto, Movimentacao, SaldoEstoque, Vendedor, Cupom, Pedido, ItemPedido

@admin.register(Fornecedor)
class FornecedorAdmin(admin.ModelAdmin):
    list_display = ("razao_social", "cnpj", "telefone", "email")
    search_fields = ("razao_social", "cnpj")

@admin.register(Deposito)
class DepositoAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "responsavel", "endereco")
    list_filter = ("tipo",)

@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ("codigo_sku", "nome", "categoria", "preco_venda", "ponto_de_pedido")
    list_filter = ("categoria",)
    search_fields = ("nome", "codigo_sku")

@admin.register(SaldoEstoque)
class SaldoEstoqueAdmin(admin.ModelAdmin):
    list_display = ("deposito", "produto", "quantidade", "alerta_ponto_pedido", "atualizado_em")
    list_filter = ("deposito",)

@admin.register(Movimentacao)
class MovimentacaoAdmin(admin.ModelAdmin):
    list_display = ("data_movimentacao", "deposito", "produto", "tipo", "quantidade", "documento_referencia")
    list_filter = ("tipo", "deposito", "data_movimentacao")

@admin.register(Vendedor)
class VendedorAdmin(admin.ModelAdmin):
    list_display = ("nome", "matricula", "email", "telefone", "ativo")
    list_filter = ("ativo",)
    search_fields = ("nome", "matricula")

@admin.register(Cupom)
class CupomAdmin(admin.ModelAdmin):
    list_display = ("codigo", "tipo_desconto", "valor_desconto", "ativo", "validade")
    list_filter = ("tipo_desconto", "ativo")
    search_fields = ("codigo",)

class ItemPedidoInline(admin.TabularInline):
    model = ItemPedido
    extra = 1

@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ("__str__", "vendedor", "cupom", "status", "criado_em")
    list_filter = ("status",)
    inlines = [ItemPedidoInline]
