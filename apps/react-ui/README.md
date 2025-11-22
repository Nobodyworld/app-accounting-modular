# React UI (Placeholder)

This directory tracks the React-based UI alternative to the Streamlit app. The
implementation intentionally remains lightweight so it can evolve without
pulling a Node toolchain into every environment.

## Proposed Stack

- Vite + React + TypeScript
- Tailwind for utility styling
- React Query for API data fetching against the FastAPI backend
- Storybook for component previews (optional)

## Getting Started (when ready)

1. Initialise the project (one-time):
   ```bash
   npm create vite@latest react-ui -- --template react-ts
   cd react-ui
   npm install
   npm install -D tailwindcss postcss autoprefixer
   npx tailwindcss init -p
   ```
2. Configure an `.env` file with `VITE_API_BASE_URL=http://localhost:8000`.
3. Run the dev server:
   ```bash
   npm run dev
   ```

## Notes

- Keep UI components stateless where possible and encapsulate API calls via a
  thin client wrapper under `src/api/`.
- Mirror key Streamlit flows first: cashflow forecast, budget variance, and
  snapshot inspection.
- Avoid committing `node_modules`; rely on the instructions above to bootstrap.
