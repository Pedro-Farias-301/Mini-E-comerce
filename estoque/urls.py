from django.contrib.auth import views as auth_views
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

    # ─── P2: Autenticação ───────────────────────────────────────────
    path("contas/login/", auth_views.LoginView.as_view(), name="login"),
    path("contas/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("contas/entrar/", views.pos_login, name="pos_login"),
    path("contas/cadastro-lojista/", views.cadastro_lojista, name="cadastro_lojista"),

    # ─── P2: Marketplace multi-vendedor ─────────────────────────────
    path("lojas/", views.lojas_lista, name="lojas_lista"),
    path("lojas/<slug:slug>/", views.loja_detalhe, name="loja_detalhe"),

    # ─── P2: Dashboard e Painel do Lojista ──────────────────────────
    path("dashboard/", views.dashboard, name="dashboard"),
    path("painel/", views.painel_lojista, name="painel_lojista"),
    path("painel/produtos/novo/", views.painel_novo_produto, name="painel_novo_produto"),
    path("painel/produtos/<int:produto_id>/editar/", views.painel_editar_produto, name="painel_editar_produto"),
    path("painel/subpedidos/<int:subpedido_id>/status/", views.painel_atualizar_status, name="painel_atualizar_status"),
]
