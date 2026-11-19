# ADR-0002: Har bir servisga PostgreSQL, lokalda SQLite

**Holat:** Qabul qilingan

## Kontekst
Servislarga tranzaksiyali, ishonchli baza kerak. Shu bilan birga, talaba va dasturchi tizimni Docker'siz ham tez ishga tushira olishi va testlar soniyalarda o'tishi kerak.

## Qaror
- Production va Docker'da har bir servis uchun alohida `postgres:16-alpine` konteyneri ishlatiladi, har biri o'z volume'i bilan.
- Lokal rejim va testlarda SQLite ishlatiladi.
- `svc_common.Database` adapteri dialekt farqlarini yashiradi:
  - parametrlar `?` ↔ `%s`;
  - birlamchi kalit `{pk}` → `SERIAL` / `AUTOINCREMENT`;
  - `RETURNING` ikkala bazada ham ishlaydi.

## Muqobillar
- **Faqat PostgreSQL (testlarda ham)**: haqiqatga yaqinroq, lekin testlar va ishga tushirish og'irlashadi.
- **ORM (SQLAlchemy)**: kuchli, lekin oddiy CRUD uchun ortiqcha murakkablik va qo'shimcha bog'liqlik.

## Oqibatlar
- ✅ `./run_local.sh` va `pytest` hech qanday infratuzilmasiz ishlaydi.
- ❌ Dialektlar farqi xavfi. Shuning uchun SQL faqat ikkala bazada ishlaydigan qism bilan cheklangan va CI'dagi integratsiya bosqichi haqiqiy PostgreSQL bilan tekshiradi.
