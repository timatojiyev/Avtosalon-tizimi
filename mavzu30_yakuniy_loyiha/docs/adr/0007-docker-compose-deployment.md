# ADR-0007: Docker Compose bilan joylashtirish

**Holat:** Qabul qilingan

## Kontekst
Bitta server, kichik jamoa. Kubernetes klasteri qimmat va murakkab.

## Qaror
Docker Compose v2 ishlatiladi. Konfiguratsiya qatlamlarga bo'lingan:
- `docker-compose.yml` — asos (servislar, healthcheck'lar, `depends_on: service_healthy`, 3 tarmoq, volume'lar, `tools` profili);
- `docker-compose.override.yml` — dev: servis portlari ochiq, matnli loglar;
- `docker-compose.prod.yml` — `read_only`, `cap_drop: ALL`, resurs limitlari, log rotatsiyasi;
- `deploy/docker-compose.deploy.yml` — serverda image'lar registry'dan olinadi.

Docker image'lar: multi-stage build, `python:3.12-slim`, non-root foydalanuvchi, `HEALTHCHECK`.

## Muqobillar
- **Kubernetes / k3s**: avtomatik tiklanish, rolling update. Bu hajm uchun ortiqcha; o'sish bosqichida o'tish mumkin.
- **systemd + virtualenv**: konteynersiz; muhitlar o'rtasida farq paydo bo'ladi.

## Oqibatlar
- ✅ Bitta buyruq bilan butun tizim ko'tariladi (dev, CI va prod'da bir xil).
- ❌ Bitta hostda ishlaydi, zero-downtime deploy yo'q (qisqa uzilish bo'ladi). Kelajak: ikkita host va blue-green deploy.
