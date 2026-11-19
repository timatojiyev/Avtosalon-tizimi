# ADR-0005: nginx API Gateway

**Holat:** Qabul qilingan

## Kontekst
Tashqaridan bir nechta port ochish xavfli va noqulay. Masshtablangan nusxalar orasida yuklamani taqsimlash kerak. So'rovni kuzatish uchun uning identifikatori kerak.

## Qaror
`nginx:alpine` tizimga yagona kirish nuqtasi bo'ladi:
- marshrutlash: `/` → web, `/api/<resurs>` → tegishli servis (v2.0 dan: faqat `X-API-Key` sarlavhasi bilan — kalit `GATEWAY_API_KEY`, nginx shabloni orqali; kalitsiz → 401);
- `limit_req` (20 so'rov/s);
- `X-Request-ID` header'ini qo'shish yoki uzatish;
- xavfsizlik header'lari;
- Docker DNS'ni o'zgaruvchi orqali qayta so'rash (scale qilingan nusxalar uchun round-robin).

## Muqobillar
- **Traefik**: Docker label'lari orqali avtomatik konfiguratsiya, lekin yana bir konsepsiyani o'rganish kerak.
- **Python'da yozilgan gateway**: moslashuvchan, lekin samaradorlik va xavfsizlik bo'yicha nginx'dan zaif.

## Oqibatlar
- ✅ Xostda faqat bitta port ochiladi, bazalar va servislar yopiq.
- ❌ Gateway yagona nosozlik nuqtasi. Production'da uni 2 nusxada yoki boshqariladigan load balancer ortida ishlatish kerak.
