# Mavzu №28 — Docker Compose yordamida ko'p servisli Python tizimini ishga tushirish

**Tizim:** “Avtosalon Tizimi”. Unda 12 ta konteyner bor:
- **gateway** — nginx, tizimga yagona kirish nuqtasi;
- **web** — boshqaruv paneli;
- 4 ta biznes-servis: `car-service`, `customer-service`, `sales-service`, `financing-service`. Har birining o'z PostgreSQL bazasi bor;
- **redis** — hodisalar navbati (Redis Streams);
- **notification-worker** — hodisalarni o'qib, mijozga xabar tayyorlaydi;
- 4 ta PostgreSQL bazasi.

Bu loyiha 27-laboratoriya ishining davomi.

```
           :8080
  brauzer ──► gateway (nginx) ──► web ──► car | customer | sales | financing ──► car-db | customer-db | sales-db | financing-db
                    └── /api/* ─────────────┘                 │
                                                              └─ XADD ─► redis (Stream) ─ XREADGROUP ─► notification-worker ×N
```

## 27-ishga nisbatan nima qo'shildi
| Imkoniyat | Qayerda |
|---|---|
| **API Gateway** (nginx): `/api/*` marshrutlash, rate limit, `X-Request-ID`, xavfsizlik header'lari, DNS orqali round-robin | `gateway/nginx.conf` |
| **Asinxron hodisalar**: sales-service → Redis Streams → notification-worker (consumer group, ack, qayta yetkazish, idempotentlik) | `libs/svc_common/events.py`, `services/notification-worker/` |
| **Masshtablash**: `--scale car-service=3 --scale notification-worker=2` | `make scale` |
| **Override fayllar**: dev (`docker-compose.override.yml`) va prod (`docker-compose.prod.yml`: resurs limitlari, `read_only`, `cap_drop: ALL`, `no-new-privileges`, log rotatsiya) | ildiz papka |
| **Profiles**: `--profile tools` → Adminer (:8081), Dozzle loglar (:8082) | `docker-compose.yml` |
| **3 ta tarmoq**: frontend / backend / data (`internal: true`) va **5 ta volume** (Redis AOF bilan) | `docker-compose.yml` |
| **Skriptlar**: `wait-healthy.sh`, `smoke-test.sh`, `Makefile` | `scripts/` |
| Panelda “Hodisalar” sahifasi va javob bergan konteyner nomi | `web/` |

## Ishga tushirish (Linux, Docker bilan)
```bash
cp .env.example .env                 # ixtiyoriy
docker compose up -d --build         # yoki: make up
scripts/wait-healthy.sh              # hamma konteyner "healthy" bo'lguncha kutish
scripts/smoke-test.sh                # gateway orqali to'liq oqimni tekshirish
```
Kirish: **http://localhost:8080** (panel), `http://localhost:8080/api/cars` (API).

| Buyruq | Vazifasi |
|---|---|
| `make scale` | car-service ×3, notification-worker ×2 (panelda “Konteyner” ustuni o'zgarib turadi) |
| `make prod` | production sozlamalari bilan |
| `make tools` | Adminer va Dozzle |
| `make logs` / `make ps` / `make down` | loglar / holat / to'xtatish |
| `make clean` | hammasini volume'lari bilan o'chirish |

## Docker'siz (tez sinov)
```bash
./run_local.sh       # 5 servis + panel; Redis o'rniga HTTP event bus, SQLite bazalar
```
Panel: http://127.0.0.1:8280

## Testlar
```bash
pip install -r requirements-dev.txt && pytest -q tests
```
Testlar quyidagilarni tekshiradi:
- har bir servis va e2e oqim;
- saga kompensatsiyasi;
- Redis Streams consumer group mantig'i (FakeRedis bilan): ack, worker qulagandan keyin qayta o'qish, dublikatlar;
- HTTP rejimdagi hodisalar oqimi.
