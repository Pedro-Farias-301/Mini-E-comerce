from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.core.exceptions import ValidationError
from .models import Fornecedor, Deposito, Produto, Movimentacao, SaldoEstoque, Vendedor, Cupom, Pedido, ItemPedido

class ControleEstoqueP1Testes(TestCase):
    def setUp(self):
        self.client = Client()
        self.fornecedor = Fornecedor.objects.create(
            razao_social="Tech Supplier", cnpj="00.111.222/0001-33", telefone="123", email="forn@tech.com"
        )
        self.loja = Deposito.objects.create(
            nome="Loja 1", tipo="loja", endereco="Rua A", responsavel="Pedro"
        )
        self.produto = Produto.objects.create(
            codigo_sku="SKU-TEST-01",
            nome="Mouse Sem Fio",
            categoria="acessorios",
            preco_custo=30.00,
            preco_venda=60.00,
            ponto_de_pedido=10,
            fornecedor_padrao=self.fornecedor
        )

    def test_todas_as_entidades_existem(self):
        self.assertEqual(Fornecedor.objects.count(), 1)
        self.assertEqual(Deposito.objects.count(), 1)
        self.assertEqual(Produto.objects.count(), 1)

    def test_rotas_principais_http_200(self):
        self.assertEqual(self.client.get(reverse("index")).status_code, 200)
        self.assertEqual(self.client.get(reverse("produtos_lista")).status_code, 200)
        self.assertEqual(self.client.get(reverse("historico")).status_code, 200)
        self.assertEqual(self.client.get(reverse("nova_movimentacao")).status_code, 200)

    def test_fluxo_movimentacao_saldo_ponto_de_pedido(self):
        # 1. Entrada de 15 peças na Loja
        res_entrada = self.client.post(reverse("nova_movimentacao"), {
            "deposito": self.loja.id,
            "produto": self.produto.id,
            "tipo": "entrada",
            "quantidade": 15,
            "fornecedor": self.fornecedor.id,
            "documento_referencia": "NF-999",
            "motivo": "Compra inicial",
        })
        self.assertEqual(res_entrada.status_code, 302)

        saldo = SaldoEstoque.objects.get(deposito=self.loja, produto=self.produto)
        self.assertEqual(saldo.quantidade, 15)
        self.assertFalse(saldo.alerta_ponto_pedido, "Com 15 peças (>10), não deve alertar ponto de pedido")

        # 2. Saída por venda no balcão de 8 peças -> Saldo cai para 7 peças
        res_venda = self.client.post(reverse("nova_movimentacao"), {
            "deposito": self.loja.id,
            "produto": self.produto.id,
            "tipo": "saida_venda",
            "quantidade": 8,
            "fornecedor": "",
            "documento_referencia": "CUPOM-102",
            "motivo": "Venda no balcão da loja",
        })
        self.assertEqual(res_venda.status_code, 302)

        saldo.refresh_from_db()
        self.assertEqual(saldo.quantidade, 7)
        self.assertTrue(saldo.alerta_ponto_pedido, "Com 7 peças (<=10), DEVE disparar alerta de ponto de pedido!")

    def test_bloqueio_saida_sem_saldo_suficiente(self):
        # Tentativa de vender 50 peças sem saldo
        mov = Movimentacao(
            deposito=self.loja,
            produto=self.produto,
            tipo="saida_venda",
            quantidade=50
        )
        with self.assertRaises(ValidationError):
            mov.clean()


class PedidoCarrinhoP1Testes(TestCase):
    """Testes das 5 entidades exigidas e do carrinho/pedido com cálculo de total."""

    def setUp(self):
        self.client = Client()
        self.vendedor = Vendedor.objects.create(
            nome="Carlos Silva", matricula="V-001", email="carlos@loja.com", telefone="11999999999"
        )
        self.cupom_perc = Cupom.objects.create(
            codigo="DESC10", tipo_desconto="percentual", valor_desconto=10, ativo=True
        )
        self.cupom_fixo = Cupom.objects.create(
            codigo="MENOS50", tipo_desconto="valor_fixo", valor_desconto=50, ativo=True
        )
        self.produto_a = Produto.objects.create(
            codigo_sku="SKU-A", nome="Teclado Mecânico", categoria="acessorios",
            preco_custo=80, preco_venda=Decimal("150.00"), ponto_de_pedido=5
        )
        self.produto_b = Produto.objects.create(
            codigo_sku="SKU-B", nome="Monitor 27\"", categoria="eletronicos",
            preco_custo=600, preco_venda=Decimal("1200.00"), ponto_de_pedido=3
        )

    def test_entidades_vendedor_cupom_pedido_item(self):
        """Verifica que Vendedor, Cupom, Pedido e ItemPedido existem."""
        self.assertEqual(Vendedor.objects.count(), 1)
        self.assertEqual(Cupom.objects.count(), 2)

        pedido = Pedido.objects.create(vendedor=self.vendedor)
        ItemPedido.objects.create(pedido=pedido, produto=self.produto_a, quantidade=2, preco_unitario=self.produto_a.preco_venda)

        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual(ItemPedido.objects.count(), 1)

    def test_rotas_pedidos_http_200(self):
        self.assertEqual(self.client.get(reverse("pedidos_lista")).status_code, 200)
        self.assertEqual(self.client.get(reverse("novo_pedido")).status_code, 200)

        pedido = Pedido.objects.create(vendedor=self.vendedor)
        self.assertEqual(self.client.get(reverse("carrinho", args=[pedido.pk])).status_code, 200)

    def test_calculo_total_sem_cupom(self):
        """Pedido com 2x Teclado (R$150) + 1x Monitor (R$1200) = R$1500."""
        pedido = Pedido.objects.create(vendedor=self.vendedor)
        ItemPedido.objects.create(pedido=pedido, produto=self.produto_a, quantidade=2, preco_unitario=self.produto_a.preco_venda)
        ItemPedido.objects.create(pedido=pedido, produto=self.produto_b, quantidade=1, preco_unitario=self.produto_b.preco_venda)

        self.assertEqual(pedido.subtotal, Decimal("1500.00"))
        self.assertEqual(pedido.valor_desconto, 0)
        self.assertEqual(pedido.total, Decimal("1500.00"))

    def test_calculo_total_com_cupom_percentual(self):
        """Cupom DESC10 (10%) sobre R$1500 = R$150 de desconto. Total = R$1350."""
        pedido = Pedido.objects.create(vendedor=self.vendedor, cupom=self.cupom_perc)
        ItemPedido.objects.create(pedido=pedido, produto=self.produto_a, quantidade=2, preco_unitario=self.produto_a.preco_venda)
        ItemPedido.objects.create(pedido=pedido, produto=self.produto_b, quantidade=1, preco_unitario=self.produto_b.preco_venda)

        self.assertEqual(pedido.subtotal, Decimal("1500.00"))
        self.assertEqual(pedido.valor_desconto, Decimal("150.00"))
        self.assertEqual(pedido.total, Decimal("1350.00"))

    def test_calculo_total_com_cupom_valor_fixo(self):
        """Cupom MENOS50 (R$50 fixo) sobre R$1500. Total = R$1450."""
        pedido = Pedido.objects.create(vendedor=self.vendedor, cupom=self.cupom_fixo)
        ItemPedido.objects.create(pedido=pedido, produto=self.produto_a, quantidade=2, preco_unitario=self.produto_a.preco_venda)
        ItemPedido.objects.create(pedido=pedido, produto=self.produto_b, quantidade=1, preco_unitario=self.produto_b.preco_venda)

        self.assertEqual(pedido.subtotal, Decimal("1500.00"))
        self.assertEqual(pedido.valor_desconto, Decimal("50"))
        self.assertEqual(pedido.total, Decimal("1450.00"))

    def test_fluxo_completo_carrinho_via_http(self):
        """Fluxo completo: criar pedido -> adicionar itens -> aplicar cupom -> finalizar."""
        # 1. Criar pedido
        res = self.client.post(reverse("novo_pedido"), {"vendedor": self.vendedor.pk, "cupom": ""})
        self.assertEqual(res.status_code, 302)
        pedido = Pedido.objects.first()
        self.assertEqual(pedido.status, "carrinho")

        # 2. Adicionar itens
        self.client.post(reverse("adicionar_item", args=[pedido.pk]), {
            "produto": self.produto_a.pk, "quantidade": 3
        })
        self.client.post(reverse("adicionar_item", args=[pedido.pk]), {
            "produto": self.produto_b.pk, "quantidade": 1
        })
        pedido.refresh_from_db()
        # 3x R$150 + 1x R$1200 = R$1650
        self.assertEqual(pedido.subtotal, Decimal("1650.00"))

        # 3. Aplicar cupom percentual (10%)
        self.client.post(reverse("aplicar_cupom", args=[pedido.pk]), {"codigo_cupom": "DESC10"})
        pedido.refresh_from_db()
        self.assertEqual(pedido.cupom, self.cupom_perc)
        self.assertEqual(pedido.total, Decimal("1485.00"))  # 1650 - 165 = 1485

        # 4. Finalizar
        res = self.client.get(reverse("finalizar_pedido", args=[pedido.pk]))
        self.assertEqual(res.status_code, 302)
        pedido.refresh_from_db()
        self.assertEqual(pedido.status, "finalizado")
        self.assertIsNotNone(pedido.finalizado_em)


class Feature1BuscaFiltroTestes(TestCase):
    """Feature 1: Busca por nome e filtro por categoria na listagem de produtos."""

    def setUp(self):
        self.client = Client()
        Produto.objects.create(codigo_sku="SKU-01", nome="Mouse Sem Fio", categoria="acessorios", preco_custo=30, preco_venda=60, ponto_de_pedido=5)
        Produto.objects.create(codigo_sku="SKU-02", nome="Teclado Mecânico", categoria="acessorios", preco_custo=80, preco_venda=150, ponto_de_pedido=5)
        Produto.objects.create(codigo_sku="SKU-03", nome="Monitor 27 polegadas", categoria="eletronicos", preco_custo=600, preco_venda=1200, ponto_de_pedido=3)
        Produto.objects.create(codigo_sku="SKU-04", nome="Cabo HDMI 2m", categoria="cabos", preco_custo=10, preco_venda=25, ponto_de_pedido=20)

    def test_busca_por_nome_icontains(self):
        """Buscar 'mouse' deve retornar apenas o Mouse Sem Fio."""
        res = self.client.get(reverse("produtos_lista"), {"q": "mouse"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.context["produtos"]), 1)
        self.assertEqual(res.context["produtos"][0].nome, "Mouse Sem Fio")

    def test_filtro_por_categoria(self):
        """Filtrar por 'acessorios' deve retornar Mouse e Teclado."""
        res = self.client.get(reverse("produtos_lista"), {"categoria": "acessorios"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.context["produtos"]), 2)

    def test_busca_e_filtro_combinados(self):
        """Buscar 'mouse' + filtrar 'acessorios' retorna 1 resultado."""
        res = self.client.get(reverse("produtos_lista"), {"q": "mouse", "categoria": "acessorios"})
        self.assertEqual(len(res.context["produtos"]), 1)

    def test_busca_e_filtro_sem_resultado(self):
        """Buscar 'mouse' + filtrar 'eletronicos' não retorna nenhum resultado."""
        res = self.client.get(reverse("produtos_lista"), {"q": "mouse", "categoria": "eletronicos"})
        self.assertEqual(len(res.context["produtos"]), 0)

    def test_sem_filtro_retorna_todos(self):
        """Sem nenhum filtro, retorna todos os 4 produtos."""
        res = self.client.get(reverse("produtos_lista"))
        self.assertEqual(len(res.context["produtos"]), 4)


class Feature2ValidacaoFormularioTestes(TestCase):
    """Feature 2: Validação customizada — preço do produto deve ser maior que zero."""

    def setUp(self):
        self.client = Client()

    def test_preco_venda_zero_invalido(self):
        """Preço de venda = 0 deve ser rejeitado com mensagem de erro."""
        form_data = {
            "codigo_sku": "SKU-INVALIDO",
            "nome": "Produto Teste",
            "categoria": "acessorios",
            "preco_custo": "10.00",
            "preco_venda": "0.00",
            "ponto_de_pedido": "5",
            "fornecedor_padrao": "",
        }
        from .forms import ProdutoForm
        form = ProdutoForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("preco_venda", form.errors)
        self.assertIn("maior que zero", form.errors["preco_venda"][0])

    def test_preco_venda_negativo_invalido(self):
        """Preço de venda negativo deve ser rejeitado."""
        from .forms import ProdutoForm
        form = ProdutoForm(data={
            "codigo_sku": "SKU-NEG", "nome": "Teste", "categoria": "acessorios",
            "preco_custo": "10.00", "preco_venda": "-5.00", "ponto_de_pedido": "5",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("preco_venda", form.errors)

    def test_preco_custo_zero_invalido(self):
        """Preço de custo = 0 deve ser rejeitado."""
        from .forms import ProdutoForm
        form = ProdutoForm(data={
            "codigo_sku": "SKU-C0", "nome": "Teste", "categoria": "acessorios",
            "preco_custo": "0.00", "preco_venda": "50.00", "ponto_de_pedido": "5",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("preco_custo", form.errors)
        self.assertIn("maior que zero", form.errors["preco_custo"][0])

    def test_precos_validos_aceitos(self):
        """Preços positivos devem ser aceitos normalmente."""
        from .forms import ProdutoForm
        form = ProdutoForm(data={
            "codigo_sku": "SKU-OK", "nome": "Produto Válido", "categoria": "acessorios",
            "preco_custo": "30.00", "preco_venda": "60.00", "ponto_de_pedido": "5",
        })
        self.assertTrue(form.is_valid())

    def test_validacao_via_http_post(self):
        """POST com preço zero deve rejeitar e não criar produto."""
        res = self.client.post(reverse("novo_produto"), {
            "codigo_sku": "SKU-HTTP", "nome": "Teste HTTP", "categoria": "acessorios",
            "preco_custo": "10.00", "preco_venda": "0.00", "ponto_de_pedido": "5",
        })
        # Não redireciona (volta para o form com erros)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(Produto.objects.filter(codigo_sku="SKU-HTTP").count(), 0)

