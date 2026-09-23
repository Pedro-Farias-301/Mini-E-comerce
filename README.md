# 📦 VarejoStock — Controle de Estoque & Gestão de Loja

**Disciplina:** Laboratório de Programação Full Stack  
**Professor:** Márcio Garrido  
**Aluno:** Pedro Barbosa Farias  
**Matrícula:** 202413692  
**Avaliação:** P1 — MVP Funcional (Aula 12)  
**Tema Escolhido:** Opção 10 — Controle de Estoque de Loja  

---

## 📌 1. Visão Geral do Projeto (P1)

Este projeto implementa o MVP funcional completo de um sistema de **Controle de Estoque e Varejo de Loja**, gerenciando fornecedores, depósitos/lojas físicas, produtos por SKU, histórico completo de movimentações (entradas e saídas por venda) e cálculo de saldos em tempo real com alertas automáticos de **Ponto de Pedido**.

### As 5 Entidades da Rubrica:
1. **`Fornecedor`**: Empresas parceiras que fornecem mercadorias para o estoque da loja.
2. **`Deposito`**: Unidades de armazenamento (Loja Física / Salão de Vendas, Depósito Central).
3. **`Produto`**: Mercadorias catalogadas com código SKU, custos, preços de venda e limite de ponto de pedido.
4. **`SaldoEstoque` (Saldo por Depósito)**: Saldo atualizado em tempo real por unidade, disparando alertas de reposição.
5. **`Movimentacao`**: Registro das entradas de notas fiscais, saídas por venda no balcão e ajustes de inventário com validação de saldo.

### Regra de Negócio P1 Implementada:
- **Movimentação e Saldo por Depósito:** Cada entrada ou saída atualiza imediatamente o inventário da loja selecionada.
- **Ponto de Pedido Automático:** O sistema monitora o saldo e emite alertas visuais de reposição assim que a quantidade atinge ou cai abaixo do estoque mínimo definido.
- **Bloqueio de Saldo Negativo:** Validação estrita impedindo vendas ou saídas superiores à disponibilidade física da unidade.

---

## 🚀 2. Como Executar

```bash
cd "Laboratório de Programação Full Stack/p1_prova/pedro"
source venv/bin/activate
python manage.py migrate
python manage.py runserver
```

Acesse: **`http://127.0.0.1:8000/`**  
Admin: **`http://127.0.0.1:8000/admin/`** (User: `admin` | Senha: `admin123`)
