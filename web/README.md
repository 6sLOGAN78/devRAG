# DevRAG Frontend (`/web`)

This directory contains the Single Page Application (SPA) for **DevRAG**, built with React and Tailwind CSS.

## Technology Stack

- **Framework**: React 18
- **Build Tool**: Vite
- **Styling**: Tailwind CSS
- **State/Data Fetching**: React Query (TanStack Query)
- **Routing**: React Router

## Architecture

The frontend connects directly to the Go API Gateway (running on port `9380`), which handles all authentication and proxies chat requests to the ML backend.

### Running Locally

```bash
cd web
npm install
npm run dev
```
The UI will be accessible at `http://localhost:5173`.
