# Avtosalon Tizimi — 26–30-topshiriqlar

| Papka | Topshiriq | Manzil |
|---|---|---|
| `lab26_avtosalon_sale_tests` | Lab 26 · 15-topshiriq — Sale agregati uchun unit testlar | http://127.0.0.1:5026 |
| `lab27_avtosalon_docker_compose` | Lab 27 · 15-topshiriq — Docker Compose: 4 servis | http://127.0.0.1:8270 |
| `mavzu28_avtosalon_multiservice` | Mavzu 28 — ko'p servisli Python tizimi | http://127.0.0.1:8280 |
| `mavzu29_avtosalon_cicd` | Mavzu 29 — CI/CD pipeline va deployment | http://127.0.0.1:8290 |
| `mavzu30_yakuniy_loyiha` | Mavzu 30 — yakuniy loyiha (arxitektura va himoya) | http://127.0.0.1:8300 |

## Hammasini bitta buyruq bilan ishga tushirish (Linux)
```bash
cd ~/Downloads/laboratoriyalar_26_30
bash start_all.sh
```
- 5 ta loyiha fonda ishga tushadi, brauzerda **index.html** ochiladi — barcha topshiriqlar ro'yxati.
  Kartaga yoki “Ochish →” tugmasiga bosing — o'sha loyiha ochiladi.
- Birinchi marta har bir loyiha o'z paketlarini o'rnatadi (internet kerak, 1–3 daqiqa).
- Yakuniy loyihaga kirish: **admin / admin123** (yana: `menejer / menejer123`, `kredit / kredit123`).

To'xtatish:
```bash
bash stop_all.sh
```

## Muammo bo'lsa
| Belgi | Yechim |
|---|---|
| `python3-venv kerak` | `sudo apt install python3-venv` |
| `⚠ ... port(lar) band` | Shu portni boshqa dastur egallagan: `sudo ss -ltnp \| grep :8300`. Agar `docker-proxy` bo'lsa — `sudo docker ps`, keyin `sudo docker stop <nom>` |
| `✗ ... ishga tushmadi` | `tail -n 30 logs/<papka_nomi>.log` — xato matnini ko'ring |
| Sahifa ochilmadi | `index.html` ni brauzerda qo'lda oching |

Faqat bitta loyihani ishga tushirish: uning papkasiga kiring va `bash run_local.sh` (Lab 26 uchun `bash run.sh`).
Docker bilan to'liq ishga tushirish (PostgreSQL, Redis, nginx) — har bir loyihaning `README.md` faylida.
