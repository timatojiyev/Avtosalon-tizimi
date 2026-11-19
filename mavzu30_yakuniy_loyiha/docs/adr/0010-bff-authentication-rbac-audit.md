# ADR-0010: Kirish nazorati web (BFF) qatlamida — login, RBAC va audit

**Holat:** Qabul qilingan (v2.0.0). ADR-0005 (gateway) ni to'ldiradi.

## Kontekst
v1.0 da panel ochiq edi: istalgan odam sotuv yaratishi yoki bekor qilishi mumkin edi. Salonda uch xil xodim bor: rahbar/administrator, sotuv menejeri va kredit mutaxassisi — ularning vazifalari va ruxsatlari har xil. Kim nima qilganini keyin aniqlash ham talab qilinadi.

## Qaror
- Foydalanuvchi faqat **web** (Backend-for-Frontend) orqali kiradi; biznes-servislar `backend` tarmog'ida, tashqaridan yopiq. Shuning uchun autentifikatsiya va ruxsat tekshiruvi **bitta joyda** — web'da.
- **Rollar va ruxsatlar** (`auth.ROLES`):

  | Ruxsat | admin | menejer | kredit |
  |---|:-:|:-:|:-:|
  | Panel, hisobotlar, hujjatlar | ✓ | ✓ | ✓ |
  | Avtomobil / mijoz qo'shish | ✓ | ✓ | — |
  | Sotuv yaratish, yakunlash, bekor qilish | ✓ | ✓ | — |
  | Kredit arizalarini ko'rish | ✓ | ✓ | ✓ |
  | Kuzatuv, chaos, CI/CD, audit, demo | ✓ | — | — |

  Har bir route `@requires("perm")` bilan belgilangan; menyu va tugmalar ham `can()` bo'yicha yashiriladi (lekin himoya serverda).
- **Parollar** `werkzeug.security` (scrypt/pbkdf2) hash ko'rinishida; production'da faqat `WEB_<LOGIN>_PASSWORD` dan olinadi, demo parollar o'chadi; `SECRET_KEY` majburiy.
- **Hujumlarga qarshi:** IP+login bo'yicha 5 xato → 5 daqiqa blok; login topilmasa ham hash tekshiriladi (timing); kirishda sessiya tozalanadi (session fixation); `next` faqat lokal yo'l (open redirect); CSRF tokeni; `HttpOnly`, `SameSite=Lax`, production'da `Secure` cookie; `X-Frame-Options: DENY`, `nosniff`.
- **Tashqi API:** gateway `/api/*` ni faqat `X-API-Key` (`GATEWAY_API_KEY`) bilan ochadi — integratsiyalar va smoke test uchun; kalitsiz so'rov 401. Production'da kalit berilmasa compose ishga tushmaydi.
- **Audit:** kirish/chiqish, barcha o'zgartirishlar, rad etilgan ruxsatlar, chaos va eksport — foydalanuvchi, IP va `request_id` bilan (iz bilan bog'lanadi). Xotirada 500 yozuv + ixtiyoriy JSONL fayl (`AUDIT_LOG_PATH`).

## Muqobillar
- **Gateway'da OIDC (Keycloak) + JWT, servislarda token tekshiruvi:** eng to'g'ri korporativ yechim, lekin alohida identity server kerak; keyingi bosqich sifatida rejalashtirilgan.
- **Har bir servisda alohida auth:** takrorlanish va xato ehtimoli ko'p.

## Oqibatlar
- ✅ Oddiy, tushunarli, to'liq test bilan qoplangan (`tests/test_final.py`).
- ✅ Servislar ichki API bo'lib qoladi — ularning kodi o'zgarmadi.
- ❌ Foydalanuvchilar konfiguratsiyada: yangi xodim qo'shish — qayta deploy. Servislar ichki tarmoqdagi chaqiruvchiga ishonadi (zero-trust emas).
