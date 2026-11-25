# 📦 VarejoStock — Controle de Estoque & Marketplace Multi-Vendedor

**Disciplina:** Laboratório de Programação Full Stack  
**Professor:** Márcio Garrido  
**Aluno:** Pedro Barbosa Farias  
**Matrícula:** 202413692  
**Avaliações:** P1 (MVP Controle de Estoque) + **P2 (Marketplace Multi-Vendedor, Dashboard & API DRF)**  
**Tema Escolhido:** Opção 10 — Controle de Estoque de Loja evoluído para Marketplace Multi-Vendedor  

---

## 📌 1. Visão Geral do Projeto (P1 + P2)

O **VarejoStock** começou na P1 como um MVP de **Controle de Estoque e Varejo de Loja** (fornecedores, depósitos, produtos por SKU, saldos em tempo real com alerta de **Ponto de Pedido**, movimentações com bloqueio de saldo negativo e carrinho com cupons de desconto) e evoluiu na **P2** para uma plataforma completa de **Marketplace Multi-Vendedor**, com **Dashboard Analítico** e **API RESTful em Django REST Framework (DRF)** documentada com OpenAPI/Swagger.

### Entidades da P1 (mantidas e integradas):
1. **`Fornecedor`**: Empresas parceiras que fornecem mercadorias.
2. **`Deposito`**: Unidades de armazenamento (Loja Física, Depósito Central, Filial).
3. **`Produto`**: Mercadorias catalogadas com SKU, preço de custo, preço de venda, ponto de pedido e vínculo com a `Loja` vendedora.
4. **`SaldoEstoque`**: Saldo em tempo real por depósito com alerta automático de ponto de pedido.
5. **`Movimentacao`**: Entradas, saídas por venda e ajustes com bloqueio de saldo negativo.
6. **`Vendedor` / `Cupom` / `Pedido` / `ItemPedido`**: Carrinho de compras com cupons percentuais ou de valor fixo.

---

## 🏪 2. Novidades da P2

### 2.1. Marketplace Multi-Vendedor (`Loja` e `SubPedido`)
- **`Loja` (Lojista / Seller)**: Cada vendedor do marketplace possui um usuário próprio (`OneToOneField` com `User`), nome, `slug` único gerado automaticamente, descrição, status (`ativa`) e taxa de comissão configurável (`comissao_percentual`, padrão 10%).
- **Catálogo Multi-Loja**:
  - Vitrine pública de lojas em `/lojas/` e página individual de cada vendedor em `/lojas/<slug>/`;
  - Filtro por vendedor na listagem geral de produtos (`/produtos/?loja=<slug>` ou `?loja=oficial`);
  - Auto-cadastro de novos vendedores em `/contas/cadastro-lojista/` (cria usuário + loja e já autentica no painel).
- **Split Automático de Pedido em Sub-pedidos (`SubPedido`)**:
  - O cliente pode adicionar produtos de **várias lojas diferentes** no mesmo carrinho (`/pedidos/<id>/carrinho/`);
  - O carrinho exibe em tempo real a **prévia da divisão por vendedor**;
  - Ao finalizar o pedido (`Pedido.finalizar()`), o sistema gera automaticamente um **`SubPedido` para cada loja envolvida**, realizando:
    1. **Rateio proporcional do cupom de desconto** conforme a participação de cada loja no subtotal;
    2. **Cálculo da comissão do marketplace** sobre a base líquida da loja (`valor_bruto - valor_desconto`);
    3. **Cálculo do repasse líquido ao lojista** (`valor_bruto - valor_desconto - valor_comissao`).
- **Painel do Lojista (`/painel/`) com Isolamento de Dados**:
  - Cada lojista gerencia apenas seus próprios produtos (`/painel/produtos/novo/` e `/painel/produtos/<id>/editar/`) — tentativas de acessar produtos de outra loja retornam `404`;
  - Controle de entrega de cada `SubPedido` com máquina de estados validada: `pendente` → `enviado` → `entregue` (ou `cancelado`).

### 2.2. Dashboard Analítico (`/dashboard/` e `/painel/`)
- **Fonte única de métricas (`estoque/dashboard.py`)**: A função `calcular_metricas(loja=None, dias=30)` alimenta tanto os templates HTML com **Chart.js** quanto o endpoint `/api/dashboard/`.
- **KPIs em tempo real**: Faturamento Bruto, Faturamento Líquido (após cupons), Receita de Comissões do Marketplace, Repasse aos Lojistas, Total de Pedidos, Itens Vendidos, Ticket Médio, Produtos/Lojas Ativas e Alertas de Estoque.
- **4 Gráficos Interativos (Chart.js) + Tabelas de Ranking**:
  1. Série histórica de faturamento diário (últimos 7, 30, 90 ou 365 dias);
  2. Vendas por categoria (gráfico de rosca);
  3. Faturamento por loja (barras horizontais) + Ranking de Lojas com comissão e repasse;
  4. Sub-pedidos por status de entrega + Top 5 produtos mais vendidos.
- **Filtro por período e por loja**: O administrador visualiza o marketplace consolidado ou filtra por uma loja específica (`/dashboard/?loja=techhouse-informatica&dias=30`); cada lojista vê automaticamente seus próprios números em `/painel/`.

### 2.3. API REST com Django REST Framework (`/api/`)
- **Autenticação**: `TokenAuthentication` (`Authorization: Token <chave>`) e `SessionAuthentication` (navegador).
- **Permissões customizadas (`estoque/api/permissions.py`)**:
  - Catálogo de lojas e produtos aberto para leitura pública (`GET`), ocultando `preco_custo` para visitantes e clientes;
  - Apenas o lojista dono do produto (ou admin) pode editar/excluir seus produtos (`EhDonoDoProdutoOuSomenteLeitura`);
  - Sub-pedidos e métricas do dashboard são filtrados automaticamente para a loja do usuário autenticado (`EhLojistaOuAdmin`).
- **Documentação OpenAPI 3 / Swagger UI**: Disponível em `/api/docs/` e schema em `/api/schema/`.

| Método | Endpoint | Descrição | Permissão |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/token/` | Obtém token de autenticação (`username` + `password`) | Público |
| `GET` | `/api/lojas/` | Lista lojas ativas do marketplace (`?search=`) | Público |
| `GET` | `/api/lojas/<slug>/` | Detalhes de uma loja | Público |
| `GET` | `/api/lojas/<slug>/produtos/` | Lista paginada dos produtos de uma loja | Público |
| `GET, POST` | `/api/produtos/` | Lista/filtra (`?categoria=`, `?loja=`, `?preco_min=`, `?preco_max=`, `?search=`) ou cadastra produto | Leitura pública / Escrita lojista ou admin |
| `GET, PATCH, DELETE` | `/api/produtos/<id>/` | Detalha, atualiza ou remove produto | Dono do produto ou admin |
| `GET, POST` | `/api/pedidos/` | Lista pedidos do cliente logado (ou todos p/ admin) e cria novo carrinho | Autenticado |
| `POST` | `/api/pedidos/<id>/itens/` | Adiciona item ao carrinho (`{"produto": id, "quantidade": n}`) | Dono do pedido ou admin |
| `DELETE` | `/api/pedidos/<id>/itens/<item_id>/` | Remove item do carrinho | Dono do pedido ou admin |
| `POST` | `/api/pedidos/<id>/aplicar-cupom/` | Aplica cupom ao carrinho (`{"codigo": "DESC10"}`) | Dono do pedido ou admin |
| `POST` | `/api/pedidos/<id>/finalizar/` | Finaliza o pedido e gera os `SubPedido` por loja | Dono do pedido ou admin |
| `GET` | `/api/subpedidos/` | Lista sub-pedidos da loja logada (ou todos p/ admin) | Lojista ou admin |
| `PATCH, POST` | `/api/subpedidos/<id>/status/` | Atualiza status de entrega (`{"status": "enviado"}`) | Lojista dono ou admin |
| `GET` | `/api/dashboard/` | KPIs e séries para gráficos (`?dias=30&loja=<slug>`) | Lojista ou admin |

---

## 🚀 3. Como Executar

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py popular_marketplace --limpar
python manage.py runserver
```

### Credenciais criadas pelo comando `popular_marketplace`:
| Perfil | Usuário | Senha | Página Principal |
| :--- | :--- | :--- | :--- |
| **Administrador** | `admin` | `admin123` | `http://127.0.0.1:8000/dashboard/` e `/admin/` |
| **Lojista 1 (TechHouse — 12%)** | `techhouse` | `lojista123` | `http://127.0.0.1:8000/painel/` |
| **Lojista 2 (Som Perfeito — 15%)** | `somperfeito` | `lojista123` | `http://127.0.0.1:8000/painel/` |
| **Lojista 3 (Conecta+ — 8%)** | `conectamais` | `lojista123` | `http://127.0.0.1:8000/painel/` |
| **Cliente Comprador** | `cliente` | `cliente123` | `http://127.0.0.1:8000/pedidos/` |

### Como rodar os testes automatizados (P1 + P2):
```bash
python manage.py test -v 2
```
