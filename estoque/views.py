from functools import wraps

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from .dashboard import calcular_metricas, normalizar_periodo, PERIODOS_VALIDOS
from .models import Deposito, Produto, Movimentacao, SaldoEstoque, Fornecedor, Vendedor, Cupom, Pedido, ItemPedido, Loja, SubPedido, loja_do_usuario
from .forms import MovimentacaoForm, ProdutoForm, PedidoForm, ItemPedidoForm, CadastroLojistaForm, ProdutoLojistaForm, SubPedidoStatusForm

def index(request):
    saldos = SaldoEstoque.objects.select_related("deposito", "produto").all()
    depositos = Deposito.objects.all()
    produtos = Produto.objects.all()
    alertas_criticos = [s for s in saldos if s.alerta_ponto_pedido]

    total_itens_estoque = sum(s.quantidade for s in saldos)

    context = {
        "saldos": saldos,
        "depositos": depositos,
        "produtos": produtos,
        "alertas_criticos": alertas_criticos,
        "total_itens_estoque": total_itens_estoque,
    }
    return render(request, "estoque/index.html", context)

def registrar_movimentacao(request):
    if request.method == "POST":
        form = MovimentacaoForm(request.POST)
        if form.is_valid():
            try:
                mov = form.save()
                messages.success(request, f"Movimentação de {mov.get_tipo_display()} registrada com sucesso! Saldo atualizado.")
                return redirect("index")
            except Exception as e:
                messages.error(request, f"Erro ao registrar: {e}")
    else:
        form = MovimentacaoForm()
    return render(request, "estoque/movimentacao_form.html", {"form": form})

def historico_movimentacoes(request):
    movs = Movimentacao.objects.select_related("deposito", "produto", "fornecedor").all()
    return render(request, "estoque/historico.html", {"movimentacoes": movs})

def produtos_lista(request):
    produtos = Produto.objects.select_related("fornecedor_padrao", "loja").prefetch_related("saldos").all()

    # Feature 1: Busca por nome do produto (campo textual)
    q = request.GET.get("q", "").strip()
    # Feature 1: Filtro por categoria (select)
    categoria = request.GET.get("categoria", "").strip()
    # P2: Filtro por loja (vendedor do marketplace) — "oficial" = produtos sem loja
    loja = request.GET.get("loja", "").strip()

    # Desafio extra: combinar busca + filtro com Q()
    filtros = Q()
    if q:
        filtros &= Q(nome__icontains=q)
    if categoria:
        filtros &= Q(categoria=categoria)
    if loja == "oficial":
        filtros &= Q(loja__isnull=True)
    elif loja:
        filtros &= Q(loja__slug=loja)

    produtos = produtos.filter(filtros)

    # Categorias disponíveis para o <select> do filtro
    categorias = Produto.CATEGORIAS

    context = {
        "produtos": produtos,
        "q": q,
        "categoria_selecionada": categoria,
        "categorias": categorias,
        "lojas": Loja.objects.filter(ativa=True),
        "loja_selecionada": loja,
    }
    return render(request, "estoque/produtos_lista.html", context)

def novo_produto(request):
    if request.method == "POST":
        form = ProdutoForm(request.POST)
        if form.is_valid():
            p = form.save()
            messages.success(request, f"Produto {p.nome} cadastrado com sucesso!")
            return redirect("produtos_lista")
    else:
        form = ProdutoForm()
    return render(request, "estoque/produto_form.html", {"form": form})

# ─── Views de Pedido / Carrinho ──────────────────────────────────────

def pedidos_lista(request):
    pedidos = Pedido.objects.select_related("vendedor", "cupom", "cliente").prefetch_related("itens__produto", "subpedidos").all()
    return render(request, "estoque/pedidos_lista.html", {"pedidos": pedidos})

def novo_pedido(request):
    if request.method == "POST":
        form = PedidoForm(request.POST)
        if form.is_valid():
            pedido = form.save(commit=False)
            if request.user.is_authenticated:
                pedido.cliente = request.user
            pedido.save()
            messages.success(request, f"Pedido #{pedido.pk} criado! Agora adicione itens ao carrinho.")
            return redirect("carrinho", pedido_id=pedido.pk)
    else:
        form = PedidoForm()
    return render(request, "estoque/pedido_form.html", {"form": form})

def carrinho(request, pedido_id):
    pedido = get_object_or_404(Pedido, pk=pedido_id)
    itens = pedido.itens.select_related("produto__loja").all()
    form = ItemPedidoForm()

    context = {
        "pedido": pedido,
        "itens": itens,
        "form": form,
        # P2: divisão do carrinho por vendedor (prévia ou sub-pedidos já gerados)
        "resumo_lojas": pedido.resumo_por_loja(),
        "subpedidos": pedido.subpedidos.select_related("loja"),
    }
    return render(request, "estoque/carrinho.html", context)

def adicionar_item(request, pedido_id):
    pedido = get_object_or_404(Pedido, pk=pedido_id)
    if pedido.status != "carrinho":
        messages.error(request, "Este pedido já foi finalizado ou cancelado.")
        return redirect("carrinho", pedido_id=pedido.pk)

    if request.method == "POST":
        form = ItemPedidoForm(request.POST)
        if form.is_valid():
            try:
                produto, quantidade = form.cleaned_data["produto"], form.cleaned_data["quantidade"]
                pedido.adicionar_item(produto, quantidade)
                messages.success(request, f"{quantidade}x {produto.nome} adicionado ao carrinho.")
            except ValidationError as e:
                messages.error(request, e.messages[0])
        else:
            messages.error(request, "Selecione um produto válido e uma quantidade maior que zero.")
    return redirect("carrinho", pedido_id=pedido.pk)

def remover_item(request, pedido_id, item_id):
    pedido = get_object_or_404(Pedido, pk=pedido_id)
    if pedido.status != "carrinho":
        messages.error(request, "Este pedido já foi finalizado ou cancelado.")
        return redirect("carrinho", pedido_id=pedido.pk)

    item = get_object_or_404(ItemPedido, pk=item_id, pedido=pedido)
    nome = item.produto.nome
    item.delete()
    messages.success(request, f"{nome} removido do carrinho.")
    return redirect("carrinho", pedido_id=pedido.pk)

def aplicar_cupom(request, pedido_id):
    pedido = get_object_or_404(Pedido, pk=pedido_id)
    if request.method == "POST":
        try:
            cupom = pedido.aplicar_cupom(request.POST.get("codigo_cupom", ""))
            messages.success(request, f"Cupom {cupom.codigo} aplicado com sucesso!")
        except ValidationError as e:
            messages.error(request, e.messages[0])
    return redirect("carrinho", pedido_id=pedido.pk)

def finalizar_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, pk=pedido_id)
    try:
        subpedidos = pedido.finalizar()
    except ValidationError as e:
        messages.error(request, e.messages[0])
        return redirect("carrinho", pedido_id=pedido.pk)

    msg = f"Pedido #{pedido.pk} finalizado com sucesso! Total: R${pedido.total:.2f}"
    if subpedidos:
        msg += f" — dividido em {len(subpedidos)} sub-pedido(s) por loja."
    messages.success(request, msg)
    return redirect("pedidos_lista")


# ═════════════════════════════════════════════════════════════════════
# P2 — Marketplace multi-vendedor, Dashboard e Painel do Lojista
# ═════════════════════════════════════════════════════════════════════

def lojista_required(view):
    """
    Define `request.loja`:
    - Se o usuário logado tiver loja própria, usa a loja dele (isolamento estrito);
    - Se for administrador ou visitante (demonstração P2), permite visualizar pela query `?loja=<slug>` ou a 1ª loja ativa;
    - Se for um usuário logado comum sem loja (ex: cliente), redireciona para cadastro de lojista.
    """

    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        loja = loja_do_usuario(request.user)
        if loja is None:
            if not request.user.is_authenticated or request.user.is_staff:
                slug = request.GET.get("loja", "").strip()
                loja = (
                    get_object_or_404(Loja, slug=slug)
                    if slug
                    else Loja.objects.filter(ativa=True).first()
                )
            if loja is None:
                messages.error(request, "Você precisa cadastrar uma loja para acessar o painel do lojista.")
                return redirect("cadastro_lojista")
        request.loja = loja
        return view(request, *args, **kwargs)

    return _wrapped


@login_required
def pos_login(request):
    """Redireciona cada perfil para sua página inicial após o login."""
    if request.user.is_staff:
        return redirect("dashboard")
    if loja_do_usuario(request.user):
        return redirect("painel_lojista")
    return redirect("lojas_lista")


def cadastro_lojista(request):
    if loja_do_usuario(request.user):
        return redirect("painel_lojista")
    if request.method == "POST":
        form = CadastroLojistaForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Bem-vindo(a)! A loja {user.loja.nome} foi criada no marketplace.")
            return redirect("painel_lojista")
    else:
        form = CadastroLojistaForm()
    return render(request, "estoque/cadastro_lojista.html", {"form": form})


def lojas_lista(request):
    lojas = Loja.objects.filter(ativa=True).annotate(total_produtos=Count("produtos"))
    return render(request, "estoque/lojas_lista.html", {"lojas": lojas})


def loja_detalhe(request, slug):
    loja = get_object_or_404(Loja, slug=slug, ativa=True)
    q = request.GET.get("q", "").strip()
    produtos = loja.produtos.prefetch_related("saldos")
    if q:
        produtos = produtos.filter(nome__icontains=q)
    return render(request, "estoque/loja_detalhe.html", {"loja": loja, "produtos": produtos, "q": q})


def _contexto_dashboard(request, loja):
    dias = normalizar_periodo(request.GET.get("dias"))
    return {"metricas": calcular_metricas(loja=loja, dias=dias), "dias": dias, "periodos": PERIODOS_VALIDOS}


def dashboard(request):
    """Dashboard global do marketplace. Lojistas logados são redirecionados ao seu painel."""
    if request.user.is_authenticated and not request.user.is_staff:
        if loja_do_usuario(request.user):
            return redirect("painel_lojista")
        raise PermissionDenied("Apenas administradores do marketplace podem ver o dashboard global.")

    loja = None
    slug = request.GET.get("loja", "").strip()
    if slug:
        loja = get_object_or_404(Loja, slug=slug)
    context = _contexto_dashboard(request, loja)
    context.update({"lojas": Loja.objects.all(), "loja_selecionada": slug})
    return render(request, "estoque/dashboard.html", context)


@lojista_required
def painel_lojista(request):
    loja = request.loja
    context = _contexto_dashboard(request, loja)
    context.update({
        "loja": loja,
        "lojas_demo": Loja.objects.filter(ativa=True) if (not request.user.is_authenticated or request.user.is_staff) else None,
        "produtos": loja.produtos.prefetch_related("saldos"),
        "subpedidos": loja.subpedidos.select_related("pedido").prefetch_related("pedido__itens__produto")[:20],
    })
    return render(request, "estoque/painel_lojista.html", context)


@lojista_required
def painel_novo_produto(request):
    form = ProdutoLojistaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        produto = form.save(commit=False)
        produto.loja = request.loja
        produto.save()
        messages.success(request, f"Produto {produto.nome} publicado na loja {request.loja.nome}!")
        return redirect("painel_lojista")
    return render(request, "estoque/produto_form.html", {
        "form": form, "titulo": f"Novo produto — {request.loja.nome}", "cancelar_url": "painel_lojista",
    })


@lojista_required
def painel_editar_produto(request, produto_id):
    # Lojista só enxerga os próprios produtos: produto de outra loja → 404
    produto = get_object_or_404(Produto, pk=produto_id, loja=request.loja)
    form = ProdutoLojistaForm(request.POST or None, instance=produto)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Produto {produto.nome} atualizado.")
        return redirect("painel_lojista")
    return render(request, "estoque/produto_form.html", {
        "form": form, "titulo": f"Editar produto — {produto.nome}", "cancelar_url": "painel_lojista",
    })


@require_POST
@lojista_required
def painel_atualizar_status(request, subpedido_id):
    if not request.user.is_authenticated or request.user.is_staff:
        subpedido = get_object_or_404(SubPedido, pk=subpedido_id)
    else:
        subpedido = get_object_or_404(SubPedido, pk=subpedido_id, loja=request.loja)
    form = SubPedidoStatusForm(request.POST)
    if form.is_valid():
        try:
            subpedido.alterar_status(form.cleaned_data["status"])
            messages.success(request, f"Sub-pedido do pedido #{subpedido.pedido_id} agora está: {subpedido.get_status_display()}.")
        except ValidationError as e:
            messages.error(request, e.messages[0])
    else:
        messages.error(request, "Status inválido.")
    return redirect("painel_lojista")
