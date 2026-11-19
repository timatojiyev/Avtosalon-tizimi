.PHONY: up down build logs ps restart clean test local psql-car psql-sales
up:        ; docker compose up -d --build
down:      ; docker compose down
build:     ; docker compose build
logs:      ; docker compose logs -f --tail=100
ps:        ; docker compose ps
restart:   ; docker compose restart
clean:     ; docker compose down -v --remove-orphans     # DIQQAT: bazalar o'chadi
test:      ; python -m pytest -q tests
local:     ; python run_local.py
psql-car:  ; docker compose exec car-db psql -U car_user -d car_db
psql-sales:; docker compose exec sales-db psql -U sales_user -d sales_db
