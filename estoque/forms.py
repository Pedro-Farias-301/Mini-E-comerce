from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Movimentacao, Produto, Deposito, Fornecedor, Vendedor, Cupom, Pedido, ItemPedido, Loja, SubPedido

class MovimentacaoForm(forms.ModelForm):
    class Meta:
        model = Movimentacao
        fields = ["deposito", "produto", "tipo", "quantidade", "fornecedor", "documento_referencia", "motivo"]
        widgets = {
            "deposito": forms.Select(attrs={"class": "form-select"}),
            "produto": forms.Select(attrs={"class": "form-select"}),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "quantidade": forms.NumberInput(attrs={"class": "form-control", "min": 1, "value": 1}),
            "fornecedor": forms.Select(attrs={"class": "form-select"}),
            "documento_referencia": forms.TextInput(attrs={"class": "form-control", "placeholder": "NF-e ou Cupom Fiscal"}),
            "motivo": forms.TextInput(attrs={"class": "form-control", "placeholder": "Observação (ex: reposição semanal)"}),
        }

class ProdutoForm(forms.ModelForm):
    class Meta:
        model = Produto
        fields = ["codigo_sku", "nome", "categoria", "preco_custo", "preco_venda", "ponto_de_pedido", "fornecedor_padrao", "loja"]
        widgets = {
            "codigo_sku": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: SKU-ELET-001"}),
            "nome": forms.TextInput(attrs={"class": "form-control"}),
            "categoria": forms.Select(attrs={"class": "form-select"}),
            "preco_custo": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "preco_venda": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "ponto_de_pedido": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "fornecedor_padrao": forms.Select(attrs={"class": "form-select"}),
            "loja": forms.Select(attrs={"class": "form-select"}),
        }

    # Feature 2: Validação customizada — o preço de venda deve ser maior que zero
    def clean_preco_venda(self):
        preco_venda = self.cleaned_data.get("preco_venda")
        if preco_venda is not None and preco_venda <= 0:
            raise forms.ValidationError(
                "O preço de venda deve ser maior que zero. Informe um valor positivo."
            )
        return preco_venda

    # Feature 2: Validação customizada — o preço de custo deve ser maior que zero
    def clean_preco_custo(self):
        preco_custo = self.cleaned_data.get("preco_custo")
        if preco_custo is not None and preco_custo <= 0:
            raise forms.ValidationError(
                "O preço de custo deve ser maior que zero. Informe um valor positivo."
            )
        return preco_custo


class ProdutoLojistaForm(ProdutoForm):
    """P2: formulário usado no painel do lojista — a loja é definida automaticamente (usuário logado)."""

    class Meta(ProdutoForm.Meta):
        fields = ["codigo_sku", "nome", "categoria", "preco_custo", "preco_venda", "ponto_de_pedido", "fornecedor_padrao"]


class PedidoForm(forms.ModelForm):
    class Meta:
        model = Pedido
        fields = ["vendedor", "cupom"]
        widgets = {
            "vendedor": forms.Select(attrs={"class": "form-select"}),
            "cupom": forms.Select(attrs={"class": "form-select"}),
        }


class ProdutoComLojaChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.nome} — R$ {obj.preco_venda:.2f} (vendido por {obj.loja_nome})"


class ItemPedidoForm(forms.ModelForm):
    produto = ProdutoComLojaChoiceField(
        queryset=Produto.objects.disponiveis().select_related("loja"),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Produto",
    )

    class Meta:
        model = ItemPedido
        fields = ["produto", "quantidade"]
        widgets = {
            "quantidade": forms.NumberInput(attrs={"class": "form-control", "min": 1, "value": 1}),
        }


# ─── P2: Marketplace ─────────────────────────────────────────────────

class CadastroLojistaForm(UserCreationForm):
    """Cria, em um único passo, o usuário de acesso e a loja do vendedor no marketplace."""

    email = forms.EmailField(label="E-mail", widget=forms.EmailInput(attrs={"class": "form-control"}))
    nome_loja = forms.CharField(label="Nome da Loja", max_length=120, widget=forms.TextInput(attrs={"class": "form-control"}))
    descricao = forms.CharField(
        label="Descrição da Loja", required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "O que sua loja vende?"}),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome in ("username", "password1", "password2"):
            self.fields[nome].widget.attrs["class"] = "form-control"

    def clean_nome_loja(self):
        nome = self.cleaned_data["nome_loja"].strip()
        if Loja.objects.filter(nome__iexact=nome).exists():
            raise forms.ValidationError("Já existe uma loja com esse nome no marketplace.")
        return nome

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
            Loja.objects.create(
                usuario=user,
                nome=self.cleaned_data["nome_loja"],
                descricao=self.cleaned_data.get("descricao", ""),
                email_contato=user.email,
            )
        return user


class SubPedidoStatusForm(forms.Form):
    status = forms.ChoiceField(choices=SubPedido.STATUS_CHOICES, widget=forms.Select(attrs={"class": "form-select"}))
