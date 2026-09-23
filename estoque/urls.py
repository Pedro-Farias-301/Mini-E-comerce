from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("movimentacao/nova/", views.registrar_movimentacao, name="nova_movimentacao"),
    path("movimentacoes/", views.historico_movimentacoes, name="historico"),
    path("produtos/", views.produtos_lista, name="produtos_lista"),
    path("produtos/novo/", views.novo_produto, name="novo_produto"),
    # Pedidos / Carrinho
    path("pedidos/", views.pedidos_lista, name="pedidos_lista"),
    path("pedidos/novo/", views.novo_pedido, name="novo_pedido"),
    path("pedidos/<int:pedido_id>/carrinho/", views.carrinho, name="carrinho"),
    path("pedidos/<int:pedido_id>/adicionar-item/", views.adicionar_item, name="adicionar_item"),
    path("pedidos/<int:pedido_id>/remover-item/<int:item_id>/", views.remover_item, name="remover_item"),
    path("pedidos/<int:pedido_id>/aplicar-cupom/", views.aplicar_cupom, name="aplicar_cupom"),
    path("pedidos/<int:pedido_id>/finalizar/", views.finalizar_pedido, name="finalizar_pedido"),
]
