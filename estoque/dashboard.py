"""
P2 — Serviço de métricas do Dashboard.

Uma única função (`calcular_metricas`) alimenta tanto o dashboard web (HTML + Chart.js)
quanto o endpoint da API (`/api/dashboard/`), garantindo que os números sejam sempre os mesmos.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import NOME_LOJA_OFICIAL, ItemPedido, Loja, Pedido, Produto, SaldoEstoque, SubPedido

PERIODOS_VALIDOS = (7, 30, 90, 365)
PERIODO_PADRAO = 30

VALOR_ITEM = F("quantidade") * F("preco_unitario")
DECIMAL = DecimalField(max_digits=14, decimal_places=2)


def normalizar_periodo(valor, padrao=PERIODO_PADRAO):
    try:
        dias = int(valor)
    except (TypeError, ValueError):
        return padrao
    return dias if dias in PERIODOS_VALIDOS else padrao


def _num(valor):
    """Converte Decimal/None em float com 2 casas (serializável em JSON)."""
    return float(round(Decimal(valor or 0), 2))


def calcular_metricas(loja=None, dias=PERIODO_PADRAO):
    """
    Calcula as métricas de vendas dos pedidos FINALIZADOS nos últimos `dias` dias.
    - loja=None  → visão do marketplace inteiro (administrador);
    - loja=<Loja> → visão restrita aos produtos/sub-pedidos daquela loja (lojista).
    """
    hoje = timezone.localdate()
    data_inicio = hoje - timedelta(days=dias - 1)
    inicio = timezone.make_aware(datetime.combine(data_inicio, time.min))

    itens = ItemPedido.objects.filter(pedido__status="finalizado", pedido__finalizado_em__gte=inicio)
    subpedidos = SubPedido.objects.filter(pedido__status="finalizado", pedido__finalizado_em__gte=inicio)
    saldos_baixos = SaldoEstoque.objects.filter(quantidade__lte=F("produto__ponto_de_pedido"))
    if loja is not None:
        itens = itens.filter(produto__loja=loja)
        subpedidos = subpedidos.filter(loja=loja)
        saldos_baixos = saldos_baixos.filter(produto__loja=loja)

    totais_itens = itens.aggregate(
        bruto=Sum(VALOR_ITEM, output_field=DECIMAL),
        qtd=Sum("quantidade"),
        pedidos=Count("pedido", distinct=True),
    )
    totais_sub = subpedidos.aggregate(
        desconto=Sum("valor_desconto"),
        comissao=Sum("valor_comissao"),
        liquido=Sum("valor_liquido"),
    )

    bruto = totais_itens["bruto"] or Decimal("0")
    pedidos_qtd = totais_itens["pedidos"] or 0

    if loja is None:
        pedidos_com_cupom = (
            Pedido.objects.filter(status="finalizado", finalizado_em__gte=inicio, cupom__isnull=False)
            .select_related("cupom")
            .prefetch_related("itens")
        )
        descontos = sum((Decimal(p.valor_desconto) for p in pedidos_com_cupom), Decimal("0"))
        produtos_ativos = Produto.objects.disponiveis().count()
    else:
        descontos = totais_sub["desconto"] or Decimal("0")
        produtos_ativos = loja.produtos.count()

    liquido_vendas = bruto - descontos
    kpis = {
        "faturamento_bruto": _num(bruto),
        "descontos": _num(descontos),
        "faturamento_liquido": _num(liquido_vendas),
        "comissao_marketplace": _num(totais_sub["comissao"]),
        "repasse_lojistas": _num(totais_sub["liquido"]),
        "pedidos": pedidos_qtd,
        "itens_vendidos": totais_itens["qtd"] or 0,
        "ticket_medio": _num(liquido_vendas / pedidos_qtd) if pedidos_qtd else 0.0,
        "produtos_ativos": produtos_ativos,
        "lojas_ativas": Loja.objects.filter(ativa=True).count(),
        "alertas_estoque": saldos_baixos.count(),
    }

    # Série diária (preenche dias sem venda com zero)
    por_dia = {
        linha["dia"]: linha
        for linha in itens.annotate(dia=TruncDate("pedido__finalizado_em"))
        .values("dia")
        .annotate(valor=Sum(VALOR_ITEM, output_field=DECIMAL), pedidos=Count("pedido", distinct=True))
    }
    vendas_por_dia = []
    for i in range(dias):
        dia = data_inicio + timedelta(days=i)
        linha = por_dia.get(dia, {})
        vendas_por_dia.append({"data": dia.isoformat(), "valor": _num(linha.get("valor")), "pedidos": linha.get("pedidos", 0)})

    vendas_por_loja = [
        {"loja": l["produto__loja__nome"] or NOME_LOJA_OFICIAL, "valor": _num(l["valor"]), "itens": l["itens"]}
        for l in itens.values("produto__loja__nome")
        .annotate(valor=Sum(VALOR_ITEM, output_field=DECIMAL), itens=Sum("quantidade"))
        .order_by("-valor")
    ]

    rotulos_categoria = dict(Produto.CATEGORIAS)
    vendas_por_categoria = [
        {"categoria": rotulos_categoria.get(c["produto__categoria"], c["produto__categoria"]), "valor": _num(c["valor"])}
        for c in itens.values("produto__categoria")
        .annotate(valor=Sum(VALOR_ITEM, output_field=DECIMAL))
        .order_by("-valor")
    ]

    top_produtos = [
        {
            "produto": p["produto__nome"],
            "sku": p["produto__codigo_sku"],
            "loja": p["produto__loja__nome"] or NOME_LOJA_OFICIAL,
            "quantidade": p["qtd"],
            "valor": _num(p["valor"]),
        }
        for p in itens.values("produto__nome", "produto__codigo_sku", "produto__loja__nome")
        .annotate(qtd=Sum("quantidade"), valor=Sum(VALOR_ITEM, output_field=DECIMAL))
        .order_by("-valor")[:5]
    ]

    rotulos_status = dict(SubPedido.STATUS_CHOICES)
    contagem_status = dict(subpedidos.values_list("status").annotate(total=Count("id")))
    subpedidos_por_status = [
        {"status": s, "label": rotulos_status[s], "total": contagem_status.get(s, 0)}
        for s, _ in SubPedido.STATUS_CHOICES
    ]

    ranking_lojas = [
        {
            "loja": r["loja__nome"],
            "slug": r["loja__slug"],
            "pedidos": r["pedidos"],
            "valor_bruto": _num(r["bruto"]),
            "comissao": _num(r["comissao"]),
            "repasse": _num(r["liquido"]),
        }
        for r in subpedidos.values("loja__nome", "loja__slug")
        .annotate(pedidos=Count("id"), bruto=Sum("valor_bruto"), comissao=Sum("valor_comissao"), liquido=Sum("valor_liquido"))
        .order_by("-bruto")
    ]

    return {
        "escopo": "loja" if loja else "marketplace",
        "loja": {"id": loja.pk, "nome": loja.nome, "slug": loja.slug} if loja else None,
        "periodo_dias": dias,
        "data_inicio": data_inicio.isoformat(),
        "data_fim": hoje.isoformat(),
        "kpis": kpis,
        "vendas_por_dia": vendas_por_dia,
        "vendas_por_loja": vendas_por_loja,
        "vendas_por_categoria": vendas_por_categoria,
        "top_produtos": top_produtos,
        "subpedidos_por_status": subpedidos_por_status,
        "ranking_lojas": ranking_lojas,
    }
