from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError

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

    class Meta:
        verbose_name = "Produto"
        verbose_name_plural = "Produtos"
        ordering = ["nome"]

    def __str__(self):
        return f"[{self.codigo_sku}] {self.nome}"

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
