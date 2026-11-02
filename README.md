> 🇺🇸 [Read this in English](README.en.md)

# ⚠️ EM DESENVOLVIMENTO ⚠️

# 🤖 Lord-Bot-Engine: De n8n para Arquitetura Python Enterprise

Um motor de atendimento automatizado, construído para escalar a operação de _delivery_ da **TheLordTrufas**. Este projeto gere um fluxo complexo de vendas via WhatsApp, atuando como o cérebro central entre o cliente, o banco de dados de produtos (Notion) e a central de atendimento humano (Chatwoot).

## 📸 Demonstração Visual (Painel ERP e Automação)

https://github.com/user-attachments/assets/f24db6c5-54d0-48eb-b09d-55ea92ab2ea6

_Visão geral do ERP construído no Notion, gerenciando pedidos, estoque e taxas de pagamento em tempo real._

---

## 💡 Filosofia do Projeto

### 1. UX Interativa vs. IA Generativa (Zero Alucinações)

O desenvolvimento deste projeto coincidiu com o pico do _hype_ em torno de agentes de atendimento baseados em Inteligência Artificial generativa (LLMs). Contudo, foi tomada a decisão arquitetural consciente de **NÃO utilizar IA generativa** no _core_ do atendimento.
Os motivos foram estritamente focados na excelência da operação:

- **Garantia da Experiência:** Em vez de respostas robóticas ou o risco de "alucinações" que poderiam prometer produtos esgotados ou preços errados, o bot foi construído com uma **Máquina de Estados Finita** extremamente rigorosa, aliada aos botões interativos e formulários nativos (Flows) do WhatsApp. Isso garante uma experiência interativa, fluida, previsível e com um tom de voz caloroso e humanizado.
- **Previsibilidade e Controle:** A estrutura mapeia 100% das intenções do utilizador sem margem para interpretações erradas pelo sistema.

### 2. Arquitetura "Zero-Cost" e Alta Eficiência

A segunda premissa fundamental foi a inovação sob **escassez de recursos**. O grande desafio técnico foi desenhar e manter um sistema de nível _Enterprise_ — rigorosamente seguro, estruturado e eficaz — utilizando **exclusivamente ferramentas, APIs e infraestruturas gratuitas** (incluindo hospedagem).
Aliado à recusa de APIs pagas de IA, isto exigiu uma otimização extrema do código e da arquitetura para garantir que, operando a custo zero, o sistema fosse altamente resiliente e livre de gargalos.

## 🚀 A Jornada da Arquitetura

O projeto evoluiu através de duas fases arquiteturais distintas para acomodar o crescimento da operação sem aumentar custos:

### Fase 1: O MVP Visual (n8n)

Iniciou-se como um ecossistema complexo no **n8n**, focado em validar a automação das vendas de forma ágil e gratuita.

- Construção de mais de 40 subfluxos lógicos independentes.
- Integração direta via webhooks com a Meta (WhatsApp Cloud API).
- Sincronização em tempo real de carrinho e estoque usando o Notion como banco de dados NoSQL.
- Implementação de suporte humano transparente usando a plataforma Chatwoot.

https://github.com/user-attachments/assets/b8e7c397-0a18-4e10-b71d-62b4d74fc75d

_Mapeamento visual da Máquina de Estados Finita operando através dos nós do n8n._

### Fase 2: Escala e Resiliência (Python Async & RabbitMQ)

Com o aumento do volume de interações e a necessidade de _background jobs_ precisos, o n8n atingiu o seu limite de performance. Para manter o custo zero e aumentar a robustez, o motor foi totalmente reescrito numa arquitetura de microsserviços em Python.

- **Desacoplamento:** Uma API FastAPI recebe os webhooks e enfileira as mensagens no **RabbitMQ**.
- **Motor Assíncrono:** Um _Worker_ em Python consome a fila ativamente e processa o estado da conversa sem bloqueios (I/O _Non-Blocking_).
- **Estado Centralizado:** Uso de um banco de dados **PostgreSQL** hospedado gratuitamente, mantendo o estado do funil de vendas seguro e persistente.

https://github.com/user-attachments/assets/f0668b7a-45ed-4102-a80d-e002bd732451

_API em Python interceptando os webhooks da Meta e enfileirando as requisições no RabbitMQ instantaneamente._

## 🛠️ Tecnologias Utilizadas (Stack 100% Gratuita)

- **Linguagem:** Python 3.11+ (100% Assíncrono usando `asyncio`)
- **Message Broker:** RabbitMQ (`aio_pika`) para tolerância a falhas e picos de tráfego.
- **Banco de Dados:** PostgreSQL (`asyncpg`) com _Connection Pooling_ avançado, proteção contra _Idle Timeouts_ e _TCP Keepalives_.
- **Integrações Externas:**
  - Meta Graph API (WhatsApp Business - Cloud API / WhatsApp Flows)
  - Notion API (Gestão de Estoque, Pedidos e Cupons)
  - Chatwoot API (Caixa de entrada para atendimento humano)

https://github.com/user-attachments/assets/9a8e8b40-3439-44ae-a6a9-3b6df65c8591

_Estrutura relacional no PostgreSQL garantindo a persistência de estado do funil de vendas._

## ⚙️ Funcionalidades Core (Engenharia)

- **Máquina de Estados de Vendas (42 Subfluxos):** Navegação de cardápio, paginação, gestão de carrinho e cálculo de frete processados milissegundo a milissegundo.
- **Intercetor de Formulários (WhatsApp Flows):** Módulo de roteamento que identifica _payloads_ JSON e converte interfaces nativas em dados de cadastro (Nome, Endereço, Avaliações).
- **Trava de Silêncio Global (Human Handoff):** Se o cliente solicitar ajuda humana, o _Worker_ altera a flag no PostgreSQL e cessa as respostas automatizadas silenciosamente.
- **Background Jobs Resilientes:** Loops assíncronos independentes (sem impacto na fila principal) para:
  - **Expiração de Atendimento:** Cálculo via _Epoch_ (à prova de fusos horários) para enviar alertas e limpar/repor estoques de carrinhos abandonados.
  - **Validação de Giftbacks e Promoções:** Limpeza automática de cupons e reversão de preços cruzando PostgreSQL e Notion.
- **Resiliência a Falhas:** Desenho à prova de _Morte Silenciosa de Conexão_ da base de dados e prevenção ativa de _Double Release_ na pool de conexões.

## 🔮 Visão de Futuro e Comercialização (Produto White-Label)

O sucesso contínuo desta arquitetura provou que é viável criar automações de altíssimo nível sem amarras a infraestruturas caras ou dependência cega de IA.

O próximo passo na evolução deste motor é o seu empacotamento como um **produto comercial focado em pequenos negócios e profissionais autônomos**. O objetivo é comercializar a infraestrutura completa — unindo o painel de gestão visual no Notion ao cérebro de atendimento em Python — como uma solução acessível (*White-Label*) para empreendedores que desejam escalar a sua operação e parar de fazer atendimentos, vendas e agendamentos de forma manual.

Ao abstrair as regras exclusivas da confeitaria, este ecossistema servirá como uma arquitetura de conversão pronta para clínicas, pequenos escritórios, lojistas e prestadores de serviço que buscam um assistente de vendas e suporte robusto.

---
