# Laboratoriya ishi №27 — 15-topshiriq

**Mavzu:** Python ilovasini Docker konteyneriga joylashtirish.

**Topshiriq:** “Avtosalon Tizimi” uchun `docker-compose.yml` yarating. 4 ta servis: `car-service`, `customer-service`, `sales-service`, `financing-service`. Har birining o'z database'i.

## Tuzilish
```
docker-compose.yml          ← asosiy fayl: 4 servis + 4 PostgreSQL + web panel
.env.example                parollar namunasi
services/
├── car-service/            Dockerfile, requirements.txt, car_service/main.py        → car-db
├── customer-service/       ...                                                       → customer-db
├── sales-service/          car/customer/financing'ni HTTP orqali chaqiradi (saga)    → sales-db
└── financing-service/      kredit arizasi, PTI ≤ 50 % qoidasi                        → financing-db
web/                        boshqaruv paneli (o'z bazasi yo'q, faqat API'lardan o'qiydi)
libs/svc_common/            umumiy kod: DB adapter, HTTP klient, /health, /ready, JSON log
tests/                      servis testlari va e2e test
run_local.py                Docker'siz ishga tushirish (SQLite)
```

## docker-compose.yml'da nima bor
- **4 ta alohida PostgreSQL** (`car-db`, `customer-db`, `sales-db`, `financing-db`), har biri o'z volume'i bilan — servislar bir-birining bazasiga ulanmaydi.
- `depends_on: condition: service_healthy` — servis o'z bazasi tayyor bo'lgandan keyin, `sales-service` esa qolgan 3 servis sog'lom bo'lgandan keyin ishga tushadi.
- Healthcheck: bazalarda `pg_isready`, servislarda `/ready` (servis + DB ulanishi).
- 3 ta tarmoq: `frontend`, `backend`, `data` (`internal: true` — bazalar tashqaridan yopiq).
- Parollar `.env` orqali (`${VAR:-default}`), `restart: unless-stopped`, YAML anchor'lar (`x-postgres`, `x-service`).
- Dockerfile'lar: multi-stage build, `python:3.12-slim`, non-root foydalanuvchi, `HEALTHCHECK`, gunicorn.

## Ishga tushirish — Docker bilan (Linux)
Talab: Docker Engine va Docker Compose v2 (`docker compose version`).
```bash
cp .env.example .env          # ixtiyoriy: parollarni o'zgartiring
docker compose up -d --build
docker compose ps             # hammasi "healthy" bo'lishini kuting (~30–60 s)
```
- Panel: **http://localhost:8080**
- API'lar: car `:8001`, customer `:8002`, sales `:8003`, financing `:8004` (masalan, `curl localhost:8001/cars`)

Foydali buyruqlar: `docker compose logs -f sales-service`, `docker compose down` (to'xtatish), `docker compose down -v` (bazalarni ham o'chirish). Yoki `make up`, `make logs`, `make down`.

## Ishga tushirish — Docker'siz (tez sinov)
```bash
./run_local.sh                # 4 servis + panel, har biri o'z SQLite fayli bilan
```
Panel: **http://127.0.0.1:8270**

## Testlar
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q tests
```
E2E test 4 servisni haqiqiy HTTP orqali ishga tushirib, naqd sotuv, tasdiqlangan va rad etilgan kreditni tekshiradi. Shuningdek, financing-service ishlamay qolganda avtomobil qayta bo'shatilishini (kompensatsiya) ham tekshiradi.
