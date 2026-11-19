# Avtosalon — ko'p servisli tizim (Mavzu №28)
COMPOSE      = docker compose
COMPOSE_BASE = docker compose -f docker-compose.yml
COMPOSE_PROD = docker compose -f docker-compose.yml -f docker-compose.prod.yml

.PHONY: up down build logs ps wait smoke scale tools prod clean test local
up:     ; $(COMPOSE) up -d --build && scripts/wait-healthy.sh
down:   ; $(COMPOSE) down
build:  ; $(COMPOSE) build
logs:   ; $(COMPOSE) logs -f --tail=100
ps:     ; $(COMPOSE) ps
wait:   ; scripts/wait-healthy.sh
smoke:  ; scripts/smoke-test.sh http://localhost:8080
scale:  ; $(COMPOSE_BASE) up -d --build --scale car-service=3 --scale notification-worker=2 && scripts/wait-healthy.sh
tools:  ; $(COMPOSE) --profile tools up -d adminer dozzle
prod:   ; $(COMPOSE_PROD) up -d --build && scripts/wait-healthy.sh
clean:  ; $(COMPOSE) --profile tools down -v --remove-orphans
test:   ; python -m pytest -q tests
local:  ; python run_local.py

# ---------------- CI/CD (Mavzu №29) ----------------
.PHONY: lint ci release deploy rollback
lint:     ; ruff check . && docker compose config --quiet
ci:       ; scripts/ci-local.sh
release:  ; @test -n "$(V)" || (echo "Foydalanish: make release V=1.1.0"; exit 1); git tag -a v$(V) -m "v$(V)" && git push origin v$(V)
deploy:   ; @test -n "$(TAG)" || (echo "Foydalanish: make deploy TAG=1.1.0 REGISTRY=ghcr.io/<owner>/avtosalon"; exit 1); bash deploy/deploy.sh $(TAG)
rollback: ; bash deploy/rollback.sh $(TAG)
