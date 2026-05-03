# PubMed Radar — AI-powered literature monitoring for clinical researchers

> **🚧 Work in progress — this project is not yet complete. I am actively working on it.**

PubMed Radar helps clinical researchers stay on top of new literature in their field. You define research topics with PubMed search queries, and the app automatically fetches new papers, summarizes them using Claude AI, and presents everything in a filterable dashboard — so you spend time *reading* papers, not *finding* them.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django 5, Django REST Framework, SimpleJWT |
| Database | PostgreSQL 16 |
| AI | Claude API (Anthropic) |
| Literature | PubMed E-utilities API |
| Infrastructure | Docker, Docker Compose |

## Quick Start

```bash
# Clone the repo
git clone https://github.com/your-username/pubmed-radar.git
cd pubmed-radar

# Copy and configure environment variables
cp .env.example .env

# Start the stack
docker-compose up
```

The API will be available at `http://localhost:8000`.

## Running Tests

```bash
cd backend
pytest --tb=short
```

## Contributing

Fork the repository and open a pull request. All contributions are welcome.

## License

MIT © 2026 Muhammad Humza Arain
