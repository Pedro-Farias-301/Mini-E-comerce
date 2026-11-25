from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.text import slugify

CENTAVOS = Decimal("0.01")
NOME_LOJA_OFICIAL = "Loja Oficial VarejoStock"


def dinheiro(valor):
    """Arredonda um valor monetário para 2 casas (meio para cima)."""
    return Decimal(valor or 0).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def loja_do_usuario(user):
    """Retorna a Loja (vendedor do marketplace) do usuário, ou None."""
    if not user or not user.is_authenticated:
        return None
    try:
        return user.loja
    except Loja.DoesNotExist:
        return None

class Fornecedor(models.Model):
    razao_social = models.CharField(max_length=150, verbose_name="Razão Social / Fornecedor")
    cnpj = models.CharField(max_length=20, unique=True, verbose_name="CNPJ")
    contato_nome = models.CharField(max_length=100, blank=True, verbose_name="Representante")
    telefone = models.CharField(max_length=20, verbose_name="Telefone")
    email = models.EmailField(verbose_name="E-mail")

    class Meta:
        verbose_name = "Fornecedor"
        verbose_name_plural = "Fornecedores"
        ordering = ["razao_social"]

    def __str__(self):
        return f"{self.razao_social} ({self.cnpj})"

class Deposito(models.Model):
    TIPO_CHOICES = [
        ("loja", "Loja Física / Salão de Vendas"),
        ("armazem", "Depósito Central / Galpão"),
        ("filial", "Filial de Distribuição"),
    ]

    nome = models.CharField(max_length=100, verbose_name="Nome da Unidade / Loja")
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="loja", verbose_name="Tipo de Instalação")
    endereco = models.CharField(max_length=200, verbose_name="Endereço")
    responsavel = models.CharField(max_length=100, verbose_name="Gerente / Encarregado")

    class Meta:
        verbose_name = "Depósito / Loja"
        verbose_name_plural = "Depósitos & Lojas"
        ordering = ["nome"]

    def __str__(self):
        return f"{self.nome} ({self.get_tipo_display()})"

# ─── P2: Marketplace Multi-Vendedor ──────────────────────────────────

class Loja(models.Model):
    """Vendedor (lojista) do marketplace. Cada loja pertence a um usuário e vende seus próprios produtos."""

    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="loja", verbose_name="Usuário Responsável")
    nome = models.CharField(max_length=120, unique=True, verbose_name="Nome da Loja")
    slug = models.SlugField(max_length=140, unique=True, blank=True, verbose_name="Slug (URL)")
    descricao = models.TextField(blank=True, verbose_name="Descrição")
    email_contato = models.EmailField(blank=True, verbose_name="E-mail de Contato")
    comissao_percentual = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("10.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        verbose_name="Comissão do Marketplace (%)",
    )
    ativa = models.BooleanField(default=True, verbose_name="Ativa")
    criada_em = models.DateTimeField(auto_now_add=True, verbose_name="Criada em")

    class Meta:
        verbose_name = "Loja (Vendedor do Marketplace)"
        verbose_name_plural = "Lojas (Vendedores do Marketplace)"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._gerar_slug_unico()
        super().save(*args, **kwargs)

    def _gerar_slug_unico(self):
        base = slugify(self.nome) or "loja"
        slug, n = base, 2
        while Loja.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f"{base}-{n}"
            n += 1
        return slug


class ProdutoQuerySet(models.QuerySet):
    def disponiveis(self):
        """Produtos da loja oficial ou de lojas ativas (aptos a serem vendidos)."""
        return self.filter(models.Q(loja__isnull=True) | models.Q(loja__ativa=True))


class Produto(models.Model):
    CATEGORIAS = [
        ("eletronicos", "Eletrônicos & Informática"),
        ("acessorios", "Acessórios & Periféricos"),
        ("audio", "Áudio & Vídeo"),
        ("cabos", "Cabos & Conectividade"),
    ]

    codigo_sku = models.CharField(max_length=30, unique=True, verbose_name="Código SKU")
    nome = models.CharField(max_length=150, verbose_name="Nome do Produto")
    categoria = models.CharField(max_length=30, choices=CATEGORIAS, default="acessorios", verbose_name="Categoria")
    preco_custo = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Preço de Custo (R$)")
    preco_venda = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Preço de Venda (R$)")
    ponto_de_pedido = models.PositiveIntegerField(default=10, verbose_name="Ponto de Pedido (Estoque Mínimo)")
    fornecedor_padrao = models.ForeignKey(Fornecedor, on_delete=models.SET_NULL, null=True, blank=True, related_name="produtos")
    # P2: produto pertence a uma loja do marketplace (vazio = loja oficial)
    loja = models.ForeignKey(
        Loja,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="produtos",
        verbose_name="Loja (Vendedor)",
        help_text="Deixe vazio para produtos da loja oficial VarejoStock.",
    )

    objects = ProdutoQuerySet.as_manager()

    class Meta:
        verbose_name = "Produto"
        verbose_name_plural = "Produtos"
        ordering = ["nome"]

    def __str__(self):
        return f"[{self.codigo_sku}] {self.nome}"

    @property
    def loja_nome(self):
        return self.loja.nome if self.loja_id else NOME_LOJA_OFICIAL

    @property
    def margem_percentual(self):
        """Margem bruta sobre o preço de venda (%)."""
        if not self.preco_venda:
            return Decimal("0")
        return (self.preco_venda - self.preco_custo) / self.preco_venda * 100

    def total_em_estoque_geral(self):
        return sum(s.quantidade for s in self.saldos.all())

class SaldoEstoque(models.Model):
    deposito = models.ForeignKey(Deposito, on_delete=models.CASCADE, related_name="saldos", verbose_name="Depósito / Loja")
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name="saldos", verbose_name="Produto")
    quantidade = models.IntegerField(default=0, verbose_name="Saldo em Estoque")
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name="Última Atualização")

    class Meta:
        verbose_name = "Saldo por Depósito"
        verbose_name_plural = "Saldos por Depósito"
        unique_together = ("deposito", "produto")

    def __str__(self):
        return f"{self.produto.nome} em {self.deposito.nome}: {self.quantidade} un"

    @property
    def alerta_ponto_pedido(self):
        return self.quantidade <= self.produto.ponto_de_pedido

class Movimentacao(models.Model):
    TIPO_MOVIMENTO = [
        ("entrada", "Entrada (Compra / Recebimento)"),
        ("saida_venda", "Saída (Venda no Balcão da Loja)"),
        ("ajuste", "Ajuste de Inventário / Perda"),
    ]

    deposito = models.ForeignKey(Deposito, on_delete=models.CASCADE, related_name="movimentacoes", verbose_name="Depósito / Loja")
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name="movimentacoes", verbose_name="Produto")
    tipo = models.CharField(max_length=20, choices=TIPO_MOVIMENTO, verbose_name="Tipo de Movimentação")
    quantidade = models.PositiveIntegerField(verbose_name="Quantidade Movimentada")
    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Fornecedor de Origem (se entrada)")
    documento_referencia = models.CharField(max_length=60, blank=True, verbose_name="Nº Nota Fiscal / Cupom Fiscal")
    motivo = models.CharField(max_length=200, blank=True, verbose_name="Observações")
    data_movimentacao = models.DateTimeField(default=timezone.now, verbose_name="Data / Hora")

    class Meta:
        verbose_name = "Movimentação de Estoque"
        verbose_name_plural = "Movimentações de Estoque"
        ordering = ["-data_movimentacao"]

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.quantidade}x {self.produto.nome} ({self.deposito.nome})"

    def clean(self):
        if self.tipo in ["saida_venda", "ajuste"]:
            saldo_obj = SaldoEstoque.objects.filter(deposito=self.deposito, produto=self.produto).first()
            saldo_atual = saldo_obj.quantidade if saldo_obj else 0
            if saldo_atual < self.quantidade:
                raise ValidationError(f"Saldo insuficiente na unidade {self.deposito.nome}. Saldo atual: {saldo_atual}, tentativa de saída: {self.quantidade}.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

        # Atualiza saldo por depósito
        saldo, _ = SaldoEstoque.objects.get_or_create(
            deposito=self.deposito,
            produto=self.produto,
            defaults={"quantidade": 0}
        )
        if self.tipo == "entrada":
            saldo.quantidade += self.quantidade
        elif self.tipo in ["saida_venda", "ajuste"]:
            saldo.quantidade -= self.quantidade
        saldo.save()


class Vendedor(models.Model):
    nome = models.CharField(max_length=150, verbose_name="Nome Completo")
    matricula = models.CharField(max_length=30, unique=True, verbose_name="Matrícula")
    email = models.EmailField(blank=True, verbose_name="E-mail")
    telefone = models.CharField(max_length=20, blank=True, verbose_name="Telefone")
    ativo = models.BooleanField(default=True, verbose_name="Ativo")

    class Meta:
        verbose_name = "Vendedor"
        verbose_name_plural = "Vendedores"
        ordering = ["nome"]

    def __str__(self):
        return f"{self.nome} ({self.matricula})"


class Cupom(models.Model):
    TIPO_DESCONTO = [
        ("percentual", "Percentual (%)"),
        ("valor_fixo", "Valor Fixo (R$)"),
    ]

    codigo = models.CharField(max_length=30, unique=True, verbose_name="Código do Cupom")
    descricao = models.CharField(max_length=200, blank=True, verbose_name="Descrição")
    tipo_desconto = models.CharField(max_length=20, choices=TIPO_DESCONTO, default="percentual", verbose_name="Tipo de Desconto")
    valor_desconto = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Valor do Desconto")
    ativo = models.BooleanField(default=True, verbose_name="Ativo")
    validade = models.DateField(null=True, blank=True, verbose_name="Validade")

    class Meta:
        verbose_name = "Cupom de Desconto"
        verbose_name_plural = "Cupons de Desconto"
        ordering = ["-ativo", "codigo"]

    def __str__(self):
        if self.tipo_desconto == "percentual":
            return f"{self.codigo} (-{self.valor_desconto}%)"
        return f"{self.codigo} (-R${self.valor_desconto})"

    @property
    def esta_valido(self):
        if not self.ativo:
            return False
        if self.validade and self.validade < timezone.now().date():
            return False
        return True


class Pedido(models.Model):
    STATUS_CHOICES = [
        ("carrinho", "Carrinho (Em Aberto)"),
        ("finalizado", "Finalizado"),
        ("cancelado", "Cancelado"),
    ]

    cliente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos", verbose_name="Cliente (Comprador)")
    vendedor = models.ForeignKey(Vendedor, on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos", verbose_name="Vendedor")
    cupom = models.ForeignKey(Cupom, on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos", verbose_name="Cupom de Desconto")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="carrinho", verbose_name="Status")
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="Data de Criação")
    finalizado_em = models.DateTimeField(null=True, blank=True, verbose_name="Data de Finalização")

    class Meta:
        verbose_name = "Pedido"
        verbose_name_plural = "Pedidos"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Pedido #{self.pk} — {self.get_status_display()}"

    @property
    def subtotal(self):
        """Soma dos subtotais de todos os itens do pedido."""
        return sum(item.subtotal for item in self.itens.all())

    @property
    def valor_desconto(self):
        """Valor do desconto aplicado pelo cupom."""
        if not self.cupom or not self.cupom.esta_valido:
            return 0
        sub = self.subtotal
        if self.cupom.tipo_desconto == "percentual":
            return round(sub * self.cupom.valor_desconto / 100, 2)
        else:
            return min(self.cupom.valor_desconto, sub)

    @property
    def total(self):
        """Total do pedido = subtotal - desconto."""
        return self.subtotal - self.valor_desconto

    # ─── P2: regras do carrinho multi-vendedor ───────────────────────

    def _validar_aberto(self):
        if self.status != "carrinho":
            raise ValidationError("Este pedido já foi finalizado ou cancelado.")

    def adicionar_item(self, produto, quantidade=1):
        """Adiciona um produto ao carrinho (somando a quantidade se o produto já estiver nele)."""
        self._validar_aberto()
        if quantidade is None or int(quantidade) < 1:
            raise ValidationError("A quantidade deve ser no mínimo 1.")
        if produto.loja_id and not produto.loja.ativa:
            raise ValidationError(f"A loja {produto.loja.nome} está inativa e não pode vender no momento.")

        item = self.itens.filter(produto=produto).first()
        if item:
            item.quantidade += int(quantidade)
            item.save(update_fields=["quantidade"])
        else:
            item = ItemPedido.objects.create(
                pedido=self, produto=produto, quantidade=int(quantidade), preco_unitario=produto.preco_venda
            )
        return item

    def aplicar_cupom(self, codigo):
        self._validar_aberto()
        codigo = (codigo or "").strip().upper()
        cupom = Cupom.objects.filter(codigo__iexact=codigo).first()
        if cupom is None:
            raise ValidationError(f"Cupom '{codigo}' não encontrado.")
        if not cupom.esta_valido:
            raise ValidationError("Este cupom está expirado ou inativo.")
        self.cupom = cupom
        self.save(update_fields=["cupom"])
        return cupom

    def resumo_por_loja(self):
        """
        Divide o pedido por vendedor (loja).
        Regras:
          - o desconto do cupom é rateado proporcionalmente ao valor de cada loja;
          - a comissão do marketplace incide sobre o valor da loja após o desconto;
          - valor líquido (repasse) = valor bruto - desconto - comissão.
        Itens sem loja pertencem à loja oficial (sem comissão/repasse).
        """
        itens = list(self.itens.select_related("produto__loja"))
        subtotal = sum((i.subtotal for i in itens), Decimal("0"))
        desconto_total = Decimal(self.valor_desconto)

        grupos = {}
        for item in itens:
            loja = item.produto.loja
            grupo = grupos.setdefault(loja.pk if loja else None, {"loja": loja, "itens": [], "bruto": Decimal("0")})
            grupo["itens"].append(item)
            grupo["bruto"] += item.subtotal

        resumo = []
        for grupo in grupos.values():
            loja, bruto = grupo["loja"], grupo["bruto"]
            desconto = dinheiro(desconto_total * bruto / subtotal) if subtotal else Decimal("0.00")
            base = bruto - desconto
            taxa = loja.comissao_percentual if loja else Decimal("0")
            comissao = dinheiro(base * taxa / 100) if loja else Decimal("0.00")
            resumo.append({
                "loja": loja,
                "loja_nome": loja.nome if loja else NOME_LOJA_OFICIAL,
                "itens": grupo["itens"],
                "valor_bruto": dinheiro(bruto),
                "valor_desconto": desconto,
                "taxa_comissao": taxa,
                "valor_comissao": comissao,
                "valor_liquido": dinheiro(base - comissao),
            })
        return sorted(resumo, key=lambda r: r["loja_nome"])

    @transaction.atomic
    def finalizar(self):
        """Finaliza o pedido e gera um SubPedido para cada loja envolvida."""
        self._validar_aberto()
        if not self.itens.exists():
            raise ValidationError("Não é possível finalizar um pedido sem itens.")

        self.status = "finalizado"
        self.finalizado_em = timezone.now()
        self.save(update_fields=["status", "finalizado_em"])

        for r in self.resumo_por_loja():
            if r["loja"] is None:
                continue
            SubPedido.objects.create(
                pedido=self,
                loja=r["loja"],
                valor_bruto=r["valor_bruto"],
                valor_desconto=r["valor_desconto"],
                taxa_comissao=r["taxa_comissao"],
                valor_comissao=r["valor_comissao"],
                valor_liquido=r["valor_liquido"],
            )
        return self.subpedidos.all()


class ItemPedido(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="itens", verbose_name="Pedido")
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name="itens_pedido", verbose_name="Produto")
    quantidade = models.PositiveIntegerField(default=1, verbose_name="Quantidade")
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Preço Unitário (R$)")

    class Meta:
        verbose_name = "Item do Pedido"
        verbose_name_plural = "Itens do Pedido"

    def __str__(self):
        return f"{self.quantidade}x {self.produto.nome} @ R${self.preco_unitario}"

    @property
    def subtotal(self):
        return self.quantidade * self.preco_unitario

    def save(self, *args, **kwargs):
        if not self.preco_unitario:
            self.preco_unitario = self.produto.preco_venda
        super().save(*args, **kwargs)



class SubPedido(models.Model):
    """
    Parte de um pedido que pertence a uma única loja do marketplace.
    Guarda um "retrato" financeiro (bruto, desconto, comissão e repasse) no momento da finalização
    e controla o fluxo de entrega daquele vendedor.
    """

    STATUS_CHOICES = [
        ("pendente", "Aguardando Envio"),
        ("enviado", "Enviado"),
        ("entregue", "Entregue"),
        ("cancelado", "Cancelado"),
    ]
    TRANSICOES = {
        "pendente": ["enviado", "cancelado"],
        "enviado": ["entregue"],
        "entregue": [],
        "cancelado": [],
    }

    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="subpedidos", verbose_name="Pedido")
    loja = models.ForeignKey(Loja, on_delete=models.PROTECT, related_name="subpedidos", verbose_name="Loja")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendente", verbose_name="Status de Entrega")
    valor_bruto = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Valor Bruto (R$)")
    valor_desconto = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Desconto Rateado (R$)")
    taxa_comissao = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="Taxa de Comissão (%)")
    valor_comissao = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Comissão do Marketplace (R$)")
    valor_liquido = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Repasse ao Lojista (R$)")
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name="Criado em")
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name="Atualizado em")

    class Meta:
        verbose_name = "Sub-pedido (por Loja)"
        verbose_name_plural = "Sub-pedidos (por Loja)"
        ordering = ["-criado_em"]
        unique_together = ("pedido", "loja")

    def __str__(self):
        return f"Pedido #{self.pedido_id} / {self.loja.nome}"

    @property
    def itens(self):
        return self.pedido.itens.filter(produto__loja=self.loja).select_related("produto")

    @property
    def proximos_status(self):
        rotulos = dict(self.STATUS_CHOICES)
        return [(s, rotulos[s]) for s in self.TRANSICOES.get(self.status, [])]

    def alterar_status(self, novo_status):
        rotulos = dict(self.STATUS_CHOICES)
        if novo_status not in rotulos:
            raise ValidationError(f"Status '{novo_status}' inválido.")
        if novo_status not in self.TRANSICOES.get(self.status, []):
            raise ValidationError(
                f"Transição inválida: {self.get_status_display()} → {rotulos[novo_status]}."
            )
        self.status = novo_status
        self.save(update_fields=["status", "atualizado_em"])
        return self
