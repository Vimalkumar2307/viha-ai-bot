# 🤖 Viha WhatsApp Lead Qualification Agent

> A production-grade LangGraph agent that qualifies return gift leads on WhatsApp — collecting requirements, matching products, and handing off to humans at the right moment.

Built for **Viha Return Gifts**, a real Indian e-commerce business selling return gifts for weddings, functions and corporate events.

---

## 🎯 What It Does

Customers message the WhatsApp number asking about return gifts. The AI agent:

1. **Greets** the customer and asks for requirements
2. **Extracts** quantity, budget, delivery location and event date from natural conversation
3. **Validates** the timeline and urgency
4. **Searches** the product catalogue for matching items
5. **Sends product images** with a requirements summary
6. **Hands off** to the human team to close the order
7. **Stays silent** — bot never interferes after human takes over

The result: wife/staff only speaks to **qualified leads** with full context already collected.

---

## 🏗️ Architecture

```
Customer (WhatsApp)
        │
        ▼
Node.js Service (Baileys)          ← WhatsApp Web connection
        │  HTTP
        ▼
Python Service (FastAPI)           ← REST API
        │
        ▼
LangGraph Agent                    ← AI brain
   ├── 7 Nodes
   ├── 3 LangChain Tools
   └── PostgreSQL Checkpointer     ← Conversation persistence
        │
        ▼
Supabase (PostgreSQL)              ← Leads + auth + state
```

---

## 🧠 LangGraph Agent Design

The agent uses a **stateful graph** with conditional routing:

```
Entry Router
    ├── New user      → Greeting Node
    └── Returning     → Intent Classifier
                            ├── Handoff (image/quick query)  → END
                            └── Browse products
                                    ↓
                            Requirement Extraction
                                    ↓
                            Validation Router
                            ├── Missing info  → Ask Confirmation → END
                            └── All collected → Validation Node
                                                      ↓
                                              Product Search
                                                      ↓
                                              Recommendation → END
```

### Nodes

| Node | Responsibility |
|---|---|
| `greeting_node` | First-time welcome message |
| `intent_classifier_node` | Classify message — product inquiry, image, quick query, unhandleable |
| `requirement_extraction_node` | Extract qty, budget, timeline, location from free text |
| `ask_confirmation_node` | Ask for missing fields or confirm ambiguous values |
| `validation_node` | Parse event date, calculate urgency level |
| `product_search_node` | Query Supabase for matching products with pricing tiers |
| `recommendation_node` | Format summary, trigger product image sending, handoff |

### Tools

| Tool | What It Does |
|---|---|
| `extract_customer_requirements` | Regex + position-based extraction for qty, budget ranges, timeline, location |
| `calculate_timeline_urgency` | Parse dates, validate future dates, assign urgency (critical/high/medium/low) |
| `search_matching_products` | Query products + variants with quantity-based pricing tiers |

---

## 📱 Human Handoff Flow

```
Bot shows products
        │
        ▼
Bot locks conversation (stays silent forever)
        │
        ▼
Staff picks up bot phone → chats with customer directly
        │
        ▼
Admin commands from wife's phone:
    RESET <number>   → Clear conversation, bot starts fresh
    UNLOCK <number>  → Re-enable bot for that customer
    LOCK <number>    → Manually silence bot
```

---

## 📊 Admin Commands (Wife's Phone)

Your wife manages everything via WhatsApp commands from her personal number:

```
SUMMARY              → Today's business overview
SUMMARY 7            → Last 7 days
SUMMARY 12/02 19/02  → Custom date range

LEADS 7              → All leads last 7 days
FOLLOWUP             → Customers silent after seeing products
PENDING              → Incomplete conversations
HOTLEADS 100         → Orders ≥ 100 pieces
UPCOMING 10          → Events in next 10 days
LOCKED               → Wife-handled conversations

INFO 919942463672    → Full customer details
RESET 919942463672   → Clear and restart conversation
UNLOCK 919942463672  → Re-enable bot
```

### Automated Reports
- ☀️ **8:00 AM IST** — Morning briefing (follow-ups + upcoming events)
- 🌟 **9:00 PM IST** — Evening summary (today's leads + hot leads)
- 📅 **Every Monday 8 AM** — Weekly report
- 🗓️ **1st of month 8 AM** — Monthly report

---

## 🛠️ Tech Stack

### Python Service
| Technology | Usage |
|---|---|
| FastAPI | REST API |
| LangGraph 0.2 | Agent state machine |
| LangChain 0.3 | Tools, prompts, LLM integration |
| Groq (Llama 3.3 70B) | LLM inference |
| psycopg3 + psycopg-pool | PostgreSQL async connection |
| Supabase PostgreSQL | Leads, checkpoints, auth |
| python-dateutil | Timeline parsing |

### Node.js Service
| Technology | Usage |
|---|---|
| Baileys | WhatsApp Web automation |
| Express | Web interface + health check |
| node-cron | Scheduled reports |
| axios | HTTP calls to Python service |
| pg | PostgreSQL for WhatsApp auth |

---

## 📁 Project Structure

```
├── node_service/
│   ├── core/
│   │   ├── vihaBot.js           ← Main WhatsApp client
│   │   ├── authStateSupabase.js ← Session persistence
│   │   ├── llmClient.js         ← Python API client
│   │   └── webInterface.js      ← Express server
│   ├── commands/
│   │   └── adminCommands.js     ← All admin command handlers
│   ├── jobs/
│   │   └── scheduledJobs.js     ← Cron reports
│   └── utils/
│       ├── messageHelper.js     ← Send text/images/alerts
│       └── dateHelper.js        ← Date range parser
│
└── python_service/
    ├── bot/
    │   ├── config.py            ← LLM setup
    │   ├── cities.py            ← Known cities for extraction
    │   ├── tools.py             ← 3 LangChain tools
    │   ├── nodes.py             ← 7 LangGraph nodes
    │   ├── graph.py             ← Graph assembly + checkpointer
    │   └── viha_bot.py          ← Public bot interface
    ├── api/
    │   ├── chat.py              ← POST /chat
    │   ├── conversations.py     ← Lock/unlock/reset
    │   ├── leads.py             ← Leads endpoints
    │   └── analytics.py        ← Summary/pending/followup/hotleads
    ├── services/
    │   ├── lead_service.py      ← Save/update leads
    │   └── lock_service.py      ← Conversation lock management
    ├── models/
    │   ├── bot_models.py        ← LangGraph state + Pydantic models
    │   └── schemas.py           ← API request/response models
    └── main.py                  ← FastAPI app entry point
```

---

## 🚀 Deployment

Both services deployed on **Render** (free tier):

- Node service — always-on WhatsApp connection
- Python service — FastAPI with auto-scaling
- Database — Supabase PostgreSQL (free tier)
- Auth persistence — WhatsApp session saved to Supabase (survives restarts)

---

## 💡 Key Design Decisions

**Why LangGraph?**
Stateful conversations need more than a simple chain. LangGraph allows conditional routing, persistent state across messages, and clean separation of concerns into nodes.

**Why two services?**
Node.js handles WhatsApp (Baileys requires Node). Python handles AI (LangChain/LangGraph ecosystem). Clean separation with HTTP between them.

**Why human handoff instead of full automation?**
Return gifts are a trust-based purchase. Customers want to speak to a real person before ordering. The bot handles the tedious data collection — humans handle the relationship.

**Why Groq?**
Fast inference (< 3 seconds per response) with Llama 3.3 70B. Free tier sufficient for current volume.

---

## 👨‍💻 Developer

Built by a .NET developer (8 years) transitioning into AI engineering.

This is a real production system serving a real business — not a tutorial project.

**Stack used:** LangGraph · LangChain · FastAPI · Groq · Supabase · Baileys · Node.js · Python