# Website Template

Base template for the AI+human website delivery service. Built with **Astro** and **Tailwind CSS**.

## Quick Start

```bash
cd website-template
npm install
npm run dev
```

## Template Structure

```
src/
├── components/
│   ├── Navbar.astro     # Sticky nav with mobile menu
│   ├── Hero.astro       # Hero section with CTAs
│   ├── Services.astro   # Services grid (6 items)
│   ├── About.astro      # About section with stats
│   ├── Contact.astro    # Contact form + info
│   └── Footer.astro     # Site footer
├── layouts/
│   └── Base.astro       # HTML shell with SEO meta
├── pages/
│   └── index.astro      # Homepage assembling all sections
└── config/
    └── site.config.ts   # Global placeholders (replace per client)
```

## Customization Per Client

All `{PLACEHOLDER}` values in components should be replaced with actual client data.

### Required Changes Before Launch

1. **Site Config** — Update `src/config/site.config.ts` with client info
2. **Navbar** — Replace `{BUSINESS_NAME}` with actual name
3. **Hero** — Update headline, subheadline, CTAs, and hero image
4. **Services** — Replace with actual services (6 items typical)
5. **About** — Update description, stats, and image
6. **Contact** — Replace address, phone, email, hours
7. **Footer** — Same as contact + copyright
8. **Forms** — Connect to Formspree/Tally endpoint

## Connecting Forms

The Contact form is a frontend-only placeholder. To enable submissions:

### Option 1: Formspree (easiest)
1. Create account at formspree.io
2. Create a form and get your form ID
3. Update the form submit handler in `Contact.astro`:
```javascript
const response = await fetch('https://formspree.io/f/YOUR_FORM_ID', {
  method: 'POST',
  body: formData,
  headers: { 'Accept': 'application/json' }
});
```

### Option 2: Tally
1. Create a form at tally.so
2. Embed the form URL in the Contact component

## Deploy

```bash
# Build for production
npm run build

# Deploy to Cloudflare Pages
wrangler pages deploy dist/ --project-name=client-name
```

## Tech Stack

- **Astro 4** — Static site generator with islands architecture
- **Tailwind CSS 3** — Utility-first CSS
- **TypeScript** — Type safety
- **Cloudflare Pages** — Free hosting with CDN

## Customization

### Brand Colors
Edit `tailwind.config.mjs` to update the `brand` color palette.

### Fonts
Replace the font family in `tailwind.config.mjs` → `fontFamily.sans`.

### Images
Replace `https://picsum.photos/` URLs with actual client images before launch.

---

*Built for the AI+human website delivery workflow*