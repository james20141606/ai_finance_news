# Global Finance Digest

![Global Finance Digest Hero](assets/hero.svg)

A twice-daily, bilingual (EN/CN) financial headlines digest with short summaries and links. Built to run fully on GitHub Actions—no local machine required.

## What It Delivers

- **Two editions daily**: New York 08:00 and Beijing 08:00 (DST handled)
- **Bilingual summaries**: English + Chinese for every item
- **Curated sources**: Mainstream financial media + macro policy feeds
- **Email-ready**: Clean, mobile-friendly HTML with a matching plain-text fallback

## How It Works

- RSS sources are fetched and normalized
- Items are deduplicated and ranked (edition-aware bias for CN vs US/global)
- Bilingual summaries are generated via free translation API
- Emails are sent via SMTP using GitHub Actions

## Quick Start (GitHub Actions)

1. Create a single secret `MAIL_FIN` in GitHub Actions (multi-line).
2. Paste the config below (replace the password):

```
FIN_RECIPIENTS=your_email@gmail.com,other@example.com
FIN_SMTP_HOST=smtp.gmail.com
FIN_SMTP_PORT=587
FIN_SMTP_USER=your_email@gmail.com
FIN_SMTP_PASS=YOUR_16_CHAR_APP_PASSWORD
FIN_SMTP_FROM=Global Finance Digest <your_email@gmail.com>
FIN_SMTP_USE_TLS=true
FIN_TRANSLATE_PROVIDER=mymemory
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
OPENAI_MODEL=gpt-5-mini
OPENAI_RERANK=true
OPENAI_CANDIDATES=50
```

3. Run the workflow: **Actions → Financial Headlines Digest → Run workflow**

## Project Layout

```
.github/workflows/fin_news_digest.yml
fin_news_digest/
  templates/
  sources.json
  run_actions.py
  digest.py
  ...
assets/hero.svg
```

## Notes

- GitHub Actions runners are stateless. If you want cross-run dedupe persistence, we can add S3/Redis.
- You can customize sources in `fin_news_digest/sources.json`.
- Email template lives in `fin_news_digest/templates/email.html`.

## Customization Ideas

- Split sections: China / US-Global / Other
- Add market snapshot blocks (S&P, FX, Bonds)
- Add a top-5 summary block at the top

---

If you want a more premium layout or additional sources, just say the word.
