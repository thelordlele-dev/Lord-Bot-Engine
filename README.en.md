> 🇧🇷 [Ler em Português](README.md)

# ⚠️ IN DEVELOPMENT ⚠️

# 🤖 Lord-Bot-Engine: From n8n to Enterprise Python Architecture

An automated customer service engine built to scale **TheLordTrufas**'s delivery operation. This project manages a complex WhatsApp sales flow, acting as the central brain between the customer, the product database (Notion), and the human support hub (Chatwoot).

## 📸 Visual Demonstration (ERP Dashboard & Automation)

https://github.com/user-attachments/assets/f24db6c5-54d0-48eb-b09d-55ea92ab2ea6

_Overview of the Notion-built ERP, managing orders, stock, and payment fees in real-time._

---

## 💡 Project Philosophy

### 1. Interactive UX vs. Generative AI (Zero Hallucinations)

The development of this project coincided with the peak hype surrounding generative Artificial Intelligence (LLM) agents. However, a conscious architectural decision was made **NOT to use generative AI** in the core customer service flow.
The reasons were strictly focused on operational excellence:

- **Experience Guarantee:** Instead of robotic responses or the risk of "hallucinations" that could promise out-of-stock products or incorrect prices, the bot was built using a strictly rigorous **Finite State Machine**, combined with WhatsApp's native interactive buttons and forms (Flows). This guarantees an interactive, fluid, predictable experience with a warm, humanized tone of voice.
- **Predictability and Control:** The structure maps 100% of user intents with no room for system misinterpretations.

### 2. "Zero-Cost" Architecture and High Efficiency

The second fundamental premise was innovation under **resource scarcity**. The major technical challenge was to design and maintain an _Enterprise-grade_ system — rigorously secure, structured, and effective — using **exclusively free tools, APIs, and infrastructure** (including hosting).
Coupled with the refusal of paid AI APIs, this required extreme code and architectural optimization to ensure that, while operating at zero cost, the system was highly resilient and bottleneck-free.

## 🚀 The Architectural Journey

The project evolved through two distinct architectural phases to accommodate operational growth without increasing costs:

### Phase 1: The Visual MVP (n8n)

It started as a complex ecosystem in **n8n**, focused on validating sales automation in an agile and cost-free manner.

- Construction of over 40 independent logical sub-flows.
- Direct integration via webhooks with Meta (WhatsApp Cloud API).
- Real-time synchronization of carts and inventory using Notion as a NoSQL database.
- Implementation of seamless human handoff using the Chatwoot platform.

https://github.com/user-attachments/assets/b8e7c397-0a18-4e10-b71d-62b4d74fc75d

_Visual mapping of the Finite State Machine operating through n8n nodes._

### Phase 2: Scale and Resilience (Async Python & RabbitMQ)

As interaction volume increased and precise background jobs became necessary, n8n reached its performance limit. To maintain zero costs and increase robustness, the engine was completely rewritten into a Python microservices architecture.

- **Decoupling:** A FastAPI receives webhooks and queues messages in **RabbitMQ**.
- **Asynchronous Engine:** A Python _Worker_ actively consumes the queue and processes the conversation state without blocking (Non-Blocking I/O).
- **Centralized State:** Use of a freely hosted **PostgreSQL** database, keeping the sales funnel state secure and persistent.

https://github.com/user-attachments/assets/f0668b7a-45ed-4102-a80d-e002bd732451

_Python API intercepting Meta webhooks and instantly queuing requests in RabbitMQ._

## 🛠️ Technologies Used (100% Free Stack)

- **Language:** Python 3.11+ (100% Asynchronous using `asyncio`)
- **Message Broker:** RabbitMQ (`aio_pika`) for fault tolerance and traffic spikes.
- **Database:** PostgreSQL (`asyncpg`) with advanced Connection Pooling, protection against Idle Timeouts, and TCP Keepalives.
- **External Integrations:**
  - Meta Graph API (WhatsApp Business - Cloud API / WhatsApp Flows)
  - Notion API (Inventory, Orders, and Coupons Management)
  - Chatwoot API (Inbox for human support)

https://github.com/user-attachments/assets/9a8e8b40-3439-44ae-a6a9-3b6df65c8591

_Relational structure in PostgreSQL ensuring persistence of the sales funnel state._

## ⚙️ Core Features (Engineering)

- **Sales State Machine (42 Sub-flows):** Menu navigation, pagination, cart management, and shipping calculation processed millisecond by millisecond.
- **Form Interceptor (WhatsApp Flows):** Routing module that identifies JSON payloads and converts native interfaces into registration data (Name, Address, Reviews).
- **Global Silence Lock (Human Handoff):** If a customer requests human help, the Worker updates the flag in PostgreSQL and silently stops automated responses.
- **Resilient Background Jobs:** Independent asynchronous loops (with no impact on the main queue) for:
  - **Session Expiration:** Epoch-based calculation (timezone-proof) to send alerts and clear/restock abandoned carts.
  - **Giftbacks and Promotions Validation:** Automatic coupon clearing and price reversion by cross-referencing PostgreSQL and Notion.
- **Fault Tolerance:** Designed to be immune to Silent Database Connection Death and active prevention of Double Release in the connection pool.

## 🔮 Future Vision and Scalability

The continuous success of this architecture proved that it is viable to create top-tier enterprise automations without being tied to expensive infrastructure or blind dependence on AI.

The next step is to evolve this engine into a **White-Label** product. The goal is to abstract the bakery's business rules and use this same optimized, deterministic, and free structure as a template to develop sales, scheduling, and support assistants for **other professions and market niches**, maintaining efficiency at zero operational cost.

---

_Note: For security reasons (API keys and TheLordTrufas's business rules), this repository is kept private. It serves as a demonstration of pragmatic software engineering, complex state management, and distributed systems integration under strict cost constraints._
