# Noytrix Trading Center — Mac demo build

This project creates an unsigned macOS ZIP containing `Noytrix Trading Center.app`.

It uses the production license endpoint and the protected Trading API. No Apple Developer account is required for this demo build. On a Mac, unzip it, then use **right click → Open** on the app the first time.

Build command:

```bash
npm install
npm run build:mac
```

The output is created in `dist/`.
