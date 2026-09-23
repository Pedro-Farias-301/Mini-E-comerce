from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from .models import Deposito, Produto, Movimentacao, SaldoEstoque, Fornecedor, Vendedor, Cupom, Pedido, ItemPedido
from .forms import MovimentacaoForm, ProdutoForm, PedidoForm, ItemPedidoForm

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
    from django.db.models import Q

    produtos = Produto.objects.select_related("fornecedor_padrao").prefetch_related("saldos").all()

    # Feature 1: Busca por nome do produto (campo textual)
    q = request.GET.get("q", "").strip()
    # Feature 1: Filtro por categoria (select)
    categoria = request.GET.get("categoria", "").strip()

    # Desafio extra: combinar busca + filtro com Q()
    filtros = Q()
    if q:
        filtros &= Q(nome__icontains=q)
    if categoria:
        filtros &= Q(categoria=categoria)

    produtos = produtos.filter(filtros)

    # Categorias disponíveis para o <select> do filtro
    categorias = Produto.CATEGORIAS

    context = {
        "produtos": produtos,
        "q": q,
        "categoria_selecionada": categoria,
        "categorias": categorias,
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
    pedidos = Pedido.objects.select_related("vendedor", "cupom").prefetch_related("itens__produto").all()
    return render(request, "estoque/pedidos_lista.html", {"pedidos": pedidos})

def novo_pedido(request):
    if request.method == "POST":
        form = PedidoForm(request.POST)
        if form.is_valid():
            pedido = form.save()
            messages.success(request, f"Pedido #{pedido.pk} criado! Agora adicione itens ao carrinho.")
            return redirect("carrinho", pedido_id=pedido.pk)
    else:
        form = PedidoForm()
    return render(request, "estoque/pedido_form.html", {"form": form})

def carrinho(request, pedido_id):
    pedido = get_object_or_404(Pedido, pk=pedido_id)
    itens = pedido.itens.select_related("produto").all()
    form = ItemPedidoForm()

    context = {
        "pedido": pedido,
        "itens": itens,
        "form": form,
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
            item = form.save(commit=False)
            item.pedido = pedido
            item.preco_unitario = item.produto.preco_venda
            item.save()
            messages.success(request, f"{item.quantidade}x {item.produto.nome} adicionado ao carrinho.")
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
    if pedido.status != "carrinho":
        messages.error(request, "Este pedido já foi finalizado ou cancelado.")
        return redirect("carrinho", pedido_id=pedido.pk)

    if request.method == "POST":
        codigo = request.POST.get("codigo_cupom", "").strip().upper()
        try:
            cupom = Cupom.objects.get(codigo__iexact=codigo)
            if cupom.esta_valido:
                pedido.cupom = cupom
                pedido.save()
                messages.success(request, f"Cupom {cupom.codigo} aplicado com sucesso!")
            else:
                messages.error(request, "Este cupom está expirado ou inativo.")
        except Cupom.DoesNotExist:
            messages.error(request, f"Cupom '{codigo}' não encontrado.")
    return redirect("carrinho", pedido_id=pedido.pk)

def finalizar_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, pk=pedido_id)
    if pedido.status != "carrinho":
        messages.error(request, "Este pedido já foi finalizado ou cancelado.")
        return redirect("carrinho", pedido_id=pedido.pk)

    if pedido.itens.count() == 0:
        messages.error(request, "Não é possível finalizar um pedido sem itens.")
        return redirect("carrinho", pedido_id=pedido.pk)

    pedido.status = "finalizado"
    pedido.finalizado_em = timezone.now()
    pedido.save()
    messages.success(request, f"Pedido #{pedido.pk} finalizado com sucesso! Total: R${pedido.total:.2f}")
    return redirect("pedidos_lista")
