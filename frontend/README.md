# Dodge AI Frontend

Next.js App Router UI for the SAP Order-to-Cash context graph.

## Setup

1. Install dependencies:
   - `npm install`
2. Create env file:
   - Copy `.env.example` to `.env.local`
3. Start app:
   - `npm run dev`

By default, the app expects backend APIs at `http://localhost:5000`.

## Backend APIs used

- `GET /graph`
- `GET /expand/:node_id`
- `POST /query` with body:
  - `{ "question": "..." }`
