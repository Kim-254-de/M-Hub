# AgriSense farmer app (Android-first, Expo)

The farmer app from the design brief: Check Crop, My Cases, Shop and Profile, in English, Kiswahili
and Gĩkũyũ (Gĩkũyũ shows Kiswahili until a translator fills `src/i18n/ki.ts`). It talks to the Django
API in `../backend`.

## Run it on your phone (Expo Go)

1. Backend, on your computer:
   ```bash
   cd ../backend
   DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,<your-LAN-IP> python manage.py runserver 0.0.0.0:8000
   python manage.py seed_demo        # optional demo data: log in with 0700 000 001, PIN 1234
   ```
   Sign-up sends a code by SMS. Without Africa's Talking set up, run Django with `REQUIRE_OTP=false`,
   or read the code from the server log (printed when `DEBUG` is on and SMS is off).
2. App:
   ```bash
   cp .env.example .env              # set EXPO_PUBLIC_API_URL to http://<your-LAN-IP>:8000
   npm install
   npx expo start
   ```
3. Install **Expo Go** from the Play Store and scan the QR code. Phone and computer must be on the
   same Wi-Fi.

## Run it in a browser (demos and UI checks)

```bash
npm run web                         # http://localhost:8081
```

With `EXPO_PUBLIC_API_URL=http://localhost:8000`, the dev backend already allows this origin. For any other
backend, add the page's origin to `DJANGO_CORS_ALLOWED_ORIGINS` there (e.g. `http://localhost:8081`).
The camera, offline queue and voice notes behave best on a real phone; test those on a device.

Checks: `npx tsc --noEmit` (types). For a real APK use EAS (`npx eas-cli@latest build -p android`).

## How it is built

| Folder | What |
|---|---|
| `src/app/` | Screens (Expo Router). `(tabs)/` is the 4-tab bottom navigation; `onboarding/` is sign-up (O1–O3), `setup-farm.tsx` is O4; `check/` is C2–C4; `case/[id]/` is C5/C6, the prescription card, follow-up and "Ask a question"; `shop/` is S2–S5; `profile/` is P2–P3. |
| `src/components/` | The brief's component library: buttons, status chip, progress tracker, case/store cards, alert card, evidence block, verification banner, photo step header, option selector, empty/error/offline states, line icons and illustrations. |
| `src/theme/tokens.ts` | Colours (all text pairs WCAG AA or better), type scale (body ≥ 16 sp), spacing, 48/56 dp touch targets. |
| `src/i18n/` | All app text in `en.ts` and `sw.ts`; `ki.ts` for the Kikuyu translator. Kiswahili wording outside the brief's sample copy is a draft for a native speaker to review. |
| `src/api/` | Typed API calls and token handling (SecureStore). |
| `src/offline/reports.ts` | Crop reports are saved on the phone first and sent step by step; with no network they wait in an outbox and go when the phone reconnects. |
| `src/lib/queries.ts` | Server data cached on the phone for a week, so the last known state shows offline. |

Rules from the brief kept throughout: exactly four tabs; one primary action per screen; every icon has
a word; colour never carries meaning alone; the AI is never the final word ("Confirmed by …").
The adviser never shows products or doses — those come only from the prescription card.
