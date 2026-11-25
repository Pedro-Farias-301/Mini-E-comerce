"""
P2 — Popula o banco com dados de demonstração do marketplace multi-vendedor.

    python manage.py popular_marketplace            # cria (se ainda não existir)
    python manage.py popular_marketplace --limpar   # apaga pedidos/lojas de demonstração e recria
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from rest_framework.authtoken.models import Token

from estoque.models import Cupom, Deposito, Fornecedor, Loja, Movimentacao, Pedido, Produto, SubPedido, Vendedor

LOJAS = [
    {
        "usuario": "techhouse", "nome": "TechHouse Informática", "comissao": "12.00",
        "descricao": "Periféricos e eletrônicos para quem trabalha e joga.",
        "produtos": [
            ("TH-001", "Teclado Mecânico RGB", "acessorios", "120.00", "249.90"),
            ("TH-002", "Mouse Gamer 16000 DPI", "acessorios", "70.00", "159.90"),
            ("TH-003", "Monitor 27\" IPS 144Hz", "eletronicos", "900.00", "1599.00"),
            ("TH-004", "SSD NVMe 1TB", "eletronicos", "260.00", "449.90"),
            ("TH-005", "Webcam Full HD", "acessorios", "90.00", "189.90"),
        ],
    },
    {
        "usuario": "somperfeito", "nome": "Som Perfeito Áudio", "comissao": "15.00",
        "descricao": "Fones, caixas de som e tudo para áudio de qualidade.",
        "produtos": [
            ("SP-001", "Fone Bluetooth ANC", "audio", "180.00", "399.90"),
            ("SP-002", "Caixa de Som Portátil", "audio", "110.00", "229.90"),
            ("SP-003", "Microfone Condensador USB", "audio", "150.00", "329.90"),
            ("SP-004", "Soundbar 2.1", "audio", "450.00", "899.00"),
        ],
    },
    {
        "usuario": "conectamais", "nome": "Conecta+ Cabos", "comissao": "8.00",
        "descricao": "Cabos, adaptadores e conectividade em geral.",
        "produtos": [
            ("CM-001", "Cabo HDMI 2.1 2m", "cabos", "18.00", "49.90"),
            ("CM-002", "Hub USB-C 7 em 1", "cabos", "85.00", "189.90"),
            ("CM-003", "Cabo de Rede Cat6 5m", "cabos", "12.00", "34.90"),
            ("CM-004", "Carregador GaN 65W", "acessorios", "95.00", "219.90"),
        ],
    },
]

PRODUTOS_OFICIAIS = [
    ("VS-001", "Notebook VarejoStock 15\"", "eletronicos", "2800.00", "3999.00"),
    ("VS-002", "Mousepad XL", "acessorios", "20.00", "59.90"),
]


class Command(BaseCommand):
    help = "Popula o banco com lojas, produtos, estoque e pedidos de demonstração do marketplace (P2)."

    def add_arguments(self, parser):
        parser.add_argument("--limpar", action="store_true", help="Remove pedidos e lojas de demonstração antes de recriar.")
        parser.add_argument("--pedidos", type=int, default=60, help="Quantidade de pedidos finalizados a gerar (padrão 60).")

    @transaction.atomic
    def handle(self, *args, **opts):
        rng = random.Random(2026)

        if opts["limpar"]:
            Pedido.objects.all().delete()
            Movimentacao.objects.all().delete()
            Produto.objects.filter(loja__isnull=False).delete()
            Produto.objects.filter(codigo_sku__in=[p[0] for p in PRODUTOS_OFICIAIS]).delete()
            Loja.objects.all().delete()
            User.objects.filter(username__in=[l["usuario"] for l in LOJAS]).delete()
            self.stdout.write(self.style.WARNING("Dados de demonstração removidos."))

        # ── Usuários ──────────────────────────────────────────────
        admin, criado = User.objects.get_or_create(username="admin", defaults={"is_staff": True, "is_superuser": True, "email": "admin@varejostock.com"})
        if criado:
            admin.set_password("admin123")
            admin.save()
        cliente, criado = User.objects.get_or_create(username="cliente", defaults={"email": "cliente@email.com", "first_name": "Cliente"})
        if criado:
            cliente.set_password("cliente123")
            cliente.save()

        # ── Cadastros básicos (P1) ────────────────────────────────
        fornecedor, _ = Fornecedor.objects.get_or_create(
            cnpj="11.222.333/0001-44",
            defaults={"razao_social": "Distribuidora Tech Brasil", "contato_nome": "Marina", "telefone": "(21) 3333-4444", "email": "vendas@techbrasil.com"},
        )
        deposito, _ = Deposito.objects.get_or_create(
            nome="Centro de Distribuição Marketplace",
            defaults={"tipo": "armazem", "endereco": "Av. Brasil, 1000 - Rio de Janeiro", "responsavel": "Pedro"},
        )
        vendedores = [
            Vendedor.objects.get_or_create(matricula="V-001", defaults={"nome": "Ana Souza", "email": "ana@varejostock.com"})[0],
            Vendedor.objects.get_or_create(matricula="V-002", defaults={"nome": "Bruno Lima", "email": "bruno@varejostock.com"})[0],
        ]
        for codigo, tipo, valor in [("DESC10", "percentual", "10"), ("MENOS50", "valor_fixo", "50"), ("BLACK15", "percentual", "15")]:
            Cupom.objects.get_or_create(codigo=codigo, defaults={"tipo_desconto": tipo, "valor_desconto": Decimal(valor), "descricao": f"Cupom {codigo}"})
        cupons = list(Cupom.objects.filter(ativo=True))

        # ── Lojas e produtos (P2) ─────────────────────────────────
        produtos = []
        for dados in LOJAS:
            user, criado = User.objects.get_or_create(username=dados["usuario"], defaults={"email": f"{dados['usuario']}@lojas.com"})
            if criado:
                user.set_password("lojista123")
                user.save()
            loja, _ = Loja.objects.get_or_create(
                usuario=user,
                defaults={"nome": dados["nome"], "descricao": dados["descricao"], "comissao_percentual": Decimal(dados["comissao"]), "email_contato": user.email},
            )
            Token.objects.get_or_create(user=user)
            for sku, nome, categoria, custo, venda in dados["produtos"]:
                produto, _ = Produto.objects.get_or_create(
                    codigo_sku=sku,
                    defaults={"nome": nome, "categoria": categoria, "preco_custo": Decimal(custo), "preco_venda": Decimal(venda),
                              "ponto_de_pedido": rng.choice([5, 8, 10]), "fornecedor_padrao": fornecedor, "loja": loja},
                )
                produtos.append(produto)
        for sku, nome, categoria, custo, venda in PRODUTOS_OFICIAIS:
            produto, _ = Produto.objects.get_or_create(
                codigo_sku=sku,
                defaults={"nome": nome, "categoria": categoria, "preco_custo": Decimal(custo), "preco_venda": Decimal(venda), "ponto_de_pedido": 5, "fornecedor_padrao": fornecedor},
            )
            produtos.append(produto)
        Token.objects.get_or_create(user=admin)
        Token.objects.get_or_create(user=cliente)

        # ── Estoque inicial ───────────────────────────────────────
        for produto in produtos:
            if not produto.saldos.exists():
                Movimentacao.objects.create(
                    deposito=deposito, produto=produto, tipo="entrada", quantidade=rng.randint(3, 60),
                    fornecedor=fornecedor, documento_referencia=f"NF-{rng.randint(1000, 9999)}", motivo="Estoque inicial (demonstração)",
                )

        # ── Pedidos finalizados espalhados nos últimos 30 dias ────
        if Pedido.objects.filter(status="finalizado").exists():
            self.stdout.write("Já existem pedidos finalizados — geração de pedidos ignorada (use --limpar para recriar).")
        else:
            agora = timezone.now()
            for _ in range(opts["pedidos"]):
                pedido = Pedido.objects.create(cliente=cliente, vendedor=rng.choice(vendedores))
                for produto in rng.sample(produtos, k=rng.randint(1, 3)):
                    pedido.adicionar_item(produto, rng.randint(1, 3))
                if rng.random() < 0.3:
                    pedido.cupom = rng.choice(cupons)
                    pedido.save(update_fields=["cupom"])
                pedido.finalizar()

                dias_atras = rng.randint(0, 29)
                quando = agora - timedelta(days=dias_atras, hours=rng.randint(0, 9), minutes=rng.randint(0, 59))
                Pedido.objects.filter(pk=pedido.pk).update(criado_em=quando - timedelta(minutes=15), finalizado_em=quando)

                for sp in pedido.subpedidos.all():
                    if dias_atras > 7:
                        novo = "entregue" if rng.random() < 0.9 else "cancelado"
                    elif dias_atras > 2:
                        novo = rng.choice(["enviado", "entregue"])
                    else:
                        novo = "pendente"
                    SubPedido.objects.filter(pk=sp.pk).update(status=novo)

            # Dois carrinhos em aberto
            for _ in range(2):
                pedido = Pedido.objects.create(cliente=cliente, vendedor=rng.choice(vendedores))
                pedido.adicionar_item(rng.choice(produtos), 1)

        # ── Resumo ────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS("\nMarketplace populado com sucesso!"))
        self.stdout.write(f"  Lojas: {Loja.objects.count()} | Produtos: {Produto.objects.count()} | "
                          f"Pedidos: {Pedido.objects.count()} | Sub-pedidos: {SubPedido.objects.count()}")
        self.stdout.write("\nCredenciais de acesso:")
        self.stdout.write("  Administrador : admin / admin123        → /dashboard/")
        for dados in LOJAS:
            token = Token.objects.get(user__username=dados["usuario"]).key
            self.stdout.write(f"  Lojista       : {dados['usuario']} / lojista123  → /painel/   (token API: {token})")
        self.stdout.write(f"  Cliente       : cliente / cliente123    (token API: {Token.objects.get(user=cliente).key})")
