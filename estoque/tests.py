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



# ═════════════════════════════════════════════════════════════════════
# Testes P2: Marketplace Multi-Vendedor, Dashboard e API DRF
# ═════════════════════════════════════════════════════════════════════

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from .models import Loja, SubPedido


class MarketplaceMultiVendedorP2Testes(TestCase):
    """Testa lojas, isolamento entre lojistas, divisão de pedido em sub-pedidos, comissões e status."""

    def setUp(self):
        self.client = Client()
        self.user_a = User.objects.create_user(username="lojista_a", password="123")
        self.loja_a = Loja.objects.create(
            usuario=self.user_a, nome="Loja Alpha", comissao_percentual=Decimal("10.00")
        )
        self.user_b = User.objects.create_user(username="lojista_b", password="123")
        self.loja_b = Loja.objects.create(
            usuario=self.user_b, nome="Loja Beta", comissao_percentual=Decimal("20.00")
        )

        self.prod_a = Produto.objects.create(
            codigo_sku="SKU-ALPHA-1",
            nome="Headset Alpha",
            categoria="audio",
            preco_custo=Decimal("100.00"),
            preco_venda=Decimal("200.00"),
            ponto_de_pedido=5,
            loja=self.loja_a,
        )
        self.prod_b = Produto.objects.create(
            codigo_sku="SKU-BETA-1",
            nome="Webcam Beta",
            categoria="acessorios",
            preco_custo=Decimal("150.00"),
            preco_venda=Decimal("300.00"),
            ponto_de_pedido=5,
            loja=self.loja_b,
        )
        self.cupom10 = Cupom.objects.create(
            codigo="MKT10", tipo_desconto="percentual", valor_desconto=Decimal("10.00"), ativo=True
        )

    def test_geracao_automatica_de_slug_unico(self):
        self.assertEqual(self.loja_a.slug, "loja-alpha")
        self.assertEqual(self.loja_b.slug, "loja-beta")

    def test_vitrine_lojas_e_filtro_por_loja(self):
        res_lojas = self.client.get(reverse("lojas_lista"))
        self.assertEqual(res_lojas.status_code, 200)
        self.assertContains(res_lojas, "Loja Alpha")
        self.assertContains(res_lojas, "Loja Beta")

        res_det = self.client.get(reverse("loja_detalhe", args=[self.loja_a.slug]))
        self.assertEqual(res_det.status_code, 200)
        self.assertContains(res_det, "Headset Alpha")
        self.assertNotContains(res_det, "Webcam Beta")

        res_filtro = self.client.get(reverse("produtos_lista"), {"loja": self.loja_a.slug})
        self.assertEqual(len(res_filtro.context["produtos"]), 1)
        self.assertEqual(res_filtro.context["produtos"][0], self.prod_a)

    def test_divisao_pedido_multi_vendedor_com_cupom_e_comissao(self):
        """
        Pedido com:
        - Loja Alpha (10% comissão): 1x R$200 = R$200 bruto
        - Loja Beta  (20% comissão): 1x R$300 = R$300 bruto
        Subtotal = R$500. Cupom MKT10 (10%) = R$50 de desconto total.
        Rateio:
        - Loja Alpha: Bruto R$200 | Desconto R$20 | Base R$180 | Comissão (10%) R$18 | Líquido R$162
        - Loja Beta : Bruto R$300 | Desconto R$30 | Base R$270 | Comissão (20%) R$54 | Líquido R$216
        """
        pedido = Pedido.objects.create(cupom=self.cupom10)
        pedido.adicionar_item(self.prod_a, 1)
        pedido.adicionar_item(self.prod_b, 1)

        subpedidos = list(pedido.finalizar())
        self.assertEqual(pedido.status, "finalizado")
        self.assertEqual(len(subpedidos), 2)

        sp_a = SubPedido.objects.get(pedido=pedido, loja=self.loja_a)
        self.assertEqual(sp_a.valor_bruto, Decimal("200.00"))
        self.assertEqual(sp_a.valor_desconto, Decimal("20.00"))
        self.assertEqual(sp_a.valor_comissao, Decimal("18.00"))
        self.assertEqual(sp_a.valor_liquido, Decimal("162.00"))

        sp_b = SubPedido.objects.get(pedido=pedido, loja=self.loja_b)
        self.assertEqual(sp_b.valor_bruto, Decimal("300.00"))
        self.assertEqual(sp_b.valor_desconto, Decimal("30.00"))
        self.assertEqual(sp_b.valor_comissao, Decimal("54.00"))
        self.assertEqual(sp_b.valor_liquido, Decimal("216.00"))

    def test_transicoes_status_subpedido(self):
        pedido = Pedido.objects.create()
        pedido.adicionar_item(self.prod_a, 1)
        pedido.finalizar()
        sp = SubPedido.objects.get(pedido=pedido, loja=self.loja_a)
        self.assertEqual(sp.status, "pendente")

        sp.alterar_status("enviado")
        self.assertEqual(sp.status, "enviado")
        sp.alterar_status("entregue")
        self.assertEqual(sp.status, "entregue")

        with self.assertRaises(ValidationError):
            sp.alterar_status("pendente")

    def test_isolamento_painel_lojista(self):
        """Lojista A acessa seu painel e edita seu produto, mas recebe 404 ao tentar editar produto da Loja B."""
        self.client.login(username="lojista_a", password="123")
        res_painel = self.client.get(reverse("painel_lojista"))
        self.assertEqual(res_painel.status_code, 200)
        self.assertContains(res_painel, "Loja Alpha")

        res_ok = self.client.get(reverse("painel_editar_produto", args=[self.prod_a.pk]))
        self.assertEqual(res_ok.status_code, 200)

        res_proibido = self.client.get(reverse("painel_editar_produto", args=[self.prod_b.pk]))
        self.assertEqual(res_proibido.status_code, 404)


class DashboardP2Testes(TestCase):
    """Testa cálculo de métricas e controle de acesso do dashboard."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(username="admin_mkt", password="123", is_staff=True)
        self.user_loja = User.objects.create_user(username="vendedor_mkt", password="123")
        self.loja = Loja.objects.create(
            usuario=self.user_loja, nome="Loja Dashboard", comissao_percentual=Decimal("10.00")
        )
        self.cliente = User.objects.create_user(username="comprador", password="123")
        self.produto = Produto.objects.create(
            codigo_sku="SKU-DASH-1",
            nome="Monitor Dashboard",
            categoria="eletronicos",
            preco_custo=Decimal("500.00"),
            preco_venda=Decimal("1000.00"),
            ponto_de_pedido=3,
            loja=self.loja,
        )
        pedido = Pedido.objects.create(cliente=self.cliente)
        pedido.adicionar_item(self.produto, 2)
        pedido.finalizar()

    def test_dashboard_admin_e_metricas(self):
        self.client.login(username="admin_mkt", password="123")
        res = self.client.get(reverse("dashboard"))
        self.assertEqual(res.status_code, 200)
        metricas = res.context["metricas"]
        self.assertEqual(metricas["escopo"], "marketplace")
        self.assertEqual(metricas["kpis"]["faturamento_bruto"], 2000.0)
        self.assertEqual(metricas["kpis"]["comissao_marketplace"], 200.0)
        self.assertEqual(metricas["kpis"]["repasse_lojistas"], 1800.0)
        self.assertEqual(metricas["kpis"]["pedidos"], 1)
        self.assertEqual(metricas["kpis"]["itens_vendidos"], 2)

    def test_dashboard_redireciona_lojista_e_bloqueia_cliente(self):
        self.client.login(username="vendedor_mkt", password="123")
        res_lojista = self.client.get(reverse("dashboard"))
        self.assertEqual(res_lojista.status_code, 302)
        self.assertEqual(res_lojista.url, reverse("painel_lojista"))

        self.client.login(username="comprador", password="123")
        res_cliente = self.client.get(reverse("dashboard"))
        self.assertEqual(res_cliente.status_code, 403)


class ApiDrfP2Testes(TestCase):
    """Testa endpoints REST do Django REST Framework, autenticação por token, permissões e fluxo de pedido."""

    def setUp(self):
        self.api = APIClient()
        self.admin = User.objects.create_user(username="admin_api", password="123", is_staff=True)
        self.user_a = User.objects.create_user(username="lojista_api_a", password="123")
        self.loja_a = Loja.objects.create(
            usuario=self.user_a, nome="ApiStore A", comissao_percentual=Decimal("10.00")
        )
        self.user_b = User.objects.create_user(username="lojista_api_b", password="123")
        self.loja_b = Loja.objects.create(
            usuario=self.user_b, nome="ApiStore B", comissao_percentual=Decimal("15.00")
        )
        self.cliente = User.objects.create_user(username="cliente_api", password="123")

        self.token_a, _ = Token.objects.get_or_create(user=self.user_a)
        self.token_b, _ = Token.objects.get_or_create(user=self.user_b)
        self.token_cliente, _ = Token.objects.get_or_create(user=self.cliente)
        self.token_admin, _ = Token.objects.get_or_create(user=self.admin)

        self.prod_a = Produto.objects.create(
            codigo_sku="API-A1",
            nome="Teclado API",
            categoria="acessorios",
            preco_custo=Decimal("80.00"),
            preco_venda=Decimal("160.00"),
            ponto_de_pedido=5,
            loja=self.loja_a,
        )
        self.prod_b = Produto.objects.create(
            codigo_sku="API-B1",
            nome="Caixa Som API",
            categoria="audio",
            preco_custo=Decimal("100.00"),
            preco_venda=Decimal("240.00"),
            ponto_de_pedido=5,
            loja=self.loja_b,
        )
        self.cupom = Cupom.objects.create(
            codigo="API10", tipo_desconto="percentual", valor_desconto=Decimal("10.00"), ativo=True
        )

    def test_catalogo_publico_lojas_e_produtos_oculta_preco_custo(self):
        res_lojas = self.api.get("/api/lojas/")
        self.assertEqual(res_lojas.status_code, 200)
        self.assertEqual(res_lojas.data["count"], 2)

        res_prods = self.api.get("/api/produtos/")
        self.assertEqual(res_prods.status_code, 200)
        self.assertEqual(res_prods.data["count"], 2)
        self.assertNotIn("preco_custo", res_prods.data["results"][0])

    def test_lojista_cria_produto_e_nao_pode_editar_produto_de_outra_loja(self):
        self.api.credentials(HTTP_AUTHORIZATION=f"Token {self.token_a.key}")
        res_create = self.api.post("/api/produtos/", {
            "codigo_sku": "API-A2",
            "nome": "Mouse API",
            "categoria": "acessorios",
            "preco_custo": "40.00",
            "preco_venda": "99.90",
            "ponto_de_pedido": 5,
        })
        self.assertEqual(res_create.status_code, 201)
        self.assertEqual(res_create.data["loja"]["slug"], self.loja_a.slug)
        self.assertIn("preco_custo", res_create.data)

        # Tentar alterar produto da Loja B deve retornar 403
        res_forbidden = self.api.patch(f"/api/produtos/{self.prod_b.pk}/", {"preco_venda": "999.00"})
        self.assertEqual(res_forbidden.status_code, 403)

    def test_fluxo_completo_pedido_e_subpedidos_via_api(self):
        # 1. Cliente cria pedido, adiciona itens de 2 lojas, aplica cupom e finaliza
        self.api.credentials(HTTP_AUTHORIZATION=f"Token {self.token_cliente.key}")
        res_ped = self.api.post("/api/pedidos/", {})
        self.assertEqual(res_ped.status_code, 201)
        pedido_id = res_ped.data["id"]

        self.assertEqual(
            self.api.post(f"/api/pedidos/{pedido_id}/itens/", {"produto": self.prod_a.pk, "quantidade": 1}).status_code,
            201,
        )
        self.assertEqual(
            self.api.post(f"/api/pedidos/{pedido_id}/itens/", {"produto": self.prod_b.pk, "quantidade": 1}).status_code,
            201,
        )
        res_cupom = self.api.post(f"/api/pedidos/{pedido_id}/aplicar-cupom/", {"codigo": "API10"})
        self.assertEqual(res_cupom.status_code, 200)
        self.assertEqual(Decimal(str(res_cupom.data["total"])), Decimal("360.00"))

        res_fin = self.api.post(f"/api/pedidos/{pedido_id}/finalizar/")
        self.assertEqual(res_fin.status_code, 200)
        self.assertEqual(res_fin.data["status"], "finalizado")
        self.assertEqual(len(res_fin.data["subpedidos"]), 2)

        # 2. Lojista A consulta seus sub-pedidos (vê apenas o dele) e avança status para 'enviado'
        self.api.credentials(HTTP_AUTHORIZATION=f"Token {self.token_a.key}")
        res_subs = self.api.get("/api/subpedidos/")
        self.assertEqual(res_subs.status_code, 200)
        self.assertEqual(res_subs.data["count"], 1)
        sub_id = res_subs.data["results"][0]["id"]

        res_status = self.api.patch(f"/api/subpedidos/{sub_id}/status/", {"status": "enviado"})
        self.assertEqual(res_status.status_code, 200)
        self.assertEqual(res_status.data["status"], "enviado")

        # 3. Dashboard via API para lojista A e para admin
        res_dash_loja = self.api.get("/api/dashboard/")
        self.assertEqual(res_dash_loja.status_code, 200)
        self.assertEqual(res_dash_loja.data["escopo"], "loja")
        self.assertEqual(res_dash_loja.data["kpis"]["faturamento_bruto"], 160.0)

        self.api.credentials(HTTP_AUTHORIZATION=f"Token {self.token_admin.key}")
        res_dash_admin = self.api.get("/api/dashboard/")
        self.assertEqual(res_dash_admin.status_code, 200)
        self.assertEqual(res_dash_admin.data["escopo"], "marketplace")
        self.assertEqual(res_dash_admin.data["kpis"]["faturamento_bruto"], 400.0)

        # 4. Schema OpenAPI e Swagger UI disponíveis
        self.assertEqual(self.api.get("/api/schema/").status_code, 200)
        self.assertEqual(self.api.get("/api/docs/").status_code, 200)
