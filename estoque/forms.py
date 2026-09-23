from django import forms
from .models import Movimentacao, Produto, Deposito, Fornecedor, Vendedor, Cupom, Pedido, ItemPedido

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
        fields = ["codigo_sku", "nome", "categoria", "preco_custo", "preco_venda", "ponto_de_pedido", "fornecedor_padrao"]
        widgets = {
            "codigo_sku": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex: SKU-ELET-001"}),
            "nome": forms.TextInput(attrs={"class": "form-control"}),
            "categoria": forms.Select(attrs={"class": "form-select"}),
            "preco_custo": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "preco_venda": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "ponto_de_pedido": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "fornecedor_padrao": forms.Select(attrs={"class": "form-select"}),
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

class PedidoForm(forms.ModelForm):
    class Meta:
        model = Pedido
        fields = ["vendedor", "cupom"]
        widgets = {
            "vendedor": forms.Select(attrs={"class": "form-select"}),
            "cupom": forms.Select(attrs={"class": "form-select"}),
        }

class ItemPedidoForm(forms.ModelForm):
    class Meta:
        model = ItemPedido
        fields = ["produto", "quantidade"]
        widgets = {
            "produto": forms.Select(attrs={"class": "form-select"}),
            "quantidade": forms.NumberInput(attrs={"class": "form-control", "min": 1, "value": 1}),
        }
