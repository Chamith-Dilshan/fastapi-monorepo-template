<div align="center">

![FastAPI](https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png)
![Next.js](https://assets.vercel.com/image/upload/v1662130559/nextjs/Icon_light_background.png)

# MonoRepo FastAPI + Next.js Template

### Production-Ready Full-Stack Application

Async FastAPI • UV • PostgreSQL • SQLAlchemy • Alembic • Docker • Traefik • GitHub Actions • Coolify

[![Python](https://img.shields.io/badge/Python-3.14%2B-blue?logo=python&logoColor=white)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-009688?logo=fastapi&logoColor=white)]()
[![Next.js](https://img.shields.io/badge/Next.js-16%2B-000000?logo=next.js&logoColor=white)]()
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-336791?logo=postgresql&logoColor=white)]()
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)]()
[![GitHub Actions](https://img.shields.io/badge/CI%2FCD-GitHub_Actions-2088FF?logo=github-actions&logoColor=white)]()

</div>

---

## 📋 Table of Contents

- [✨ Features](#-features)
- [🏗️ Architecture](#-architecture)
- [🚀 Quick Start](#-quick-start)
- [📁 Project Structure](#-project-structure)
- [🛠️ Tech Stack](#-tech-stack)
- [📚 Documentation](#-documentation)
- [🤝 Contributing](#-contributing)

---

## ✨ Features

### Backend (FastAPI)

- ⚡ **Async Architecture** — High-performance async endpoints with FastAPI
- 🗄️ **PostgreSQL + SQLAlchemy** — Robust relational database with ORM
- 🔄 **Alembic Migrations** — Version control for database schema
- 🔐 **JWT Authentication** — Secure token-based auth
- 🔒 **Argon2 Password Hashing** — Industry-standard password security
- 📧 **Email Verification** — Password recovery & email-based flows
- 🧪 **Pytest + Coverage** — Comprehensive test suite
- 📊 **Data Validation** — Pydantic models for request/response validation
- 🧹 **Code Quality** — Ruff, Black, Pyrefly linting
- sentry, open telimitry

### Frontend (Next.js)

- 🎨 **Tailwind CSS + shadcn/ui** — Modern, accessible UI components
- 📱 **Responsive Design** — Mobile-first approach
- 🌙 **Dark Mode** — Built-in dark/light theme support
- 🔄 **TypeScript** — Type-safe React components
- 🤖 **Auto-Generated Client** — Type-safe API client from OpenAPI spec
- 🧪 **Playwright E2E Tests** — End-to-end testing
- ⚡ **App Router** — Latest Next.js routing with async components

### DevOps & Deployment

- 🐳 **Docker & Docker Compose** — Containerized local development & production
- 🔀 **Traefik Reverse Proxy** — Automatic HTTPS, load balancing
- 📬 **Resend** — email
- ✉️ **React Email** — Templated email rendering
- 🚀 **Gunicorn + Uvicorn** — Production-grade ASGI server
- 🎯 **Coolify** — Simplified self-hosted deployment
- 🔄 **GitHub Actions CI/CD** — Automated testing, building, deployment

---

## 🏗️ Architecture

````text
monorepo/
├── frontend/                         # Next.js App Router
│   ├── app/                          # Route groups & pages
│   ├── components/                   # Reusable React components
│   ├── lib/                          # Utilities & API client
│   ├── public/                       # Static assets
│   ├── styles/                       # Global styles
│   ├── package.json
│   └── tsconfig.json
│
├── backend/                          # FastAPI async backend
│   ├── app/
│   │   ├── api/                      # API routes
│   │   ├── core/                     # Config, security, logging
│   │   ├── db/                       # Database models & session
│   │   ├── models/                   # Pydantic schemas
│   │   ├── crud/                     # Database operations
│   │   ├── dependencies/             # Dependency injection
│   │   ├── tasks/                    # Async tasks, email
│   │   └── main.py                   # FastAPI app entry
│   ├── tests/                        # Pytest test suite
│   ├── alembic/                      # Database migrations
│   ├── pyproject.toml
│   └── .env.example
│
├── docker-compose.yml                # Local dev & production configs
├── Makefile                          # Orchestration commands
├── .github/
│   └── workflows/                    # GitHub Actions CI/CD
└── README.md
````

---

## 🚀 Quick Start

### Prerequisites

- **Python** 3.9+
- **Node.js** 18+ & npm/pnpm
- **Docker & Docker Compose** (optional, for containerized setup)
- **UV** (Fast Python package manager)

### Installation & Development

```bash
# 1. Clone the repository
git clone <repo-url>
cd my-monorepo

# 2. Install dependencies
make install

# 3. Setup environment variables
cp backend/.env.example backend/.env
# Edit backend/.env with your settings

# 4. Setup database (first time only)
cd backend
uv run alembic upgrade head
cd ..

# 5. Run development servers
make dev
# Backend: http://localhost:8000
# Frontend: http://localhost:3000
# API Docs: http://localhost:8000/docs

````

Or with Docker Compose:

````bash
docker-compose up -d
````

🔐 Security Features
✅ JWT Token Authentication — Secure, stateless auth
✅ Argon2 Password Hashing — Modern, resistant to GPU attacks
✅ CORS Configuration — Controlled cross-origin requests
✅ HTTPS/TLS — Automatic with Traefik (production)
✅ Environment Secrets — Never committed to git
✅ SQL Injection Prevention — SQLAlchemy parameterized queries
✅ CSRF Protection — Built into forms and API

🚢 Deployment
With Coolify
bash

# Push to your repository and connect via Coolify UI

# Automatic builds & deployments from git commits

With Docker Compose (Self-Hosted)
bash

docker-compose -f docker-compose.prod.yml up -d
Environment Variables
Set these in your deployment platform:

env

DATABASE\_URL=postgresql://user:password@db:5432/dbname
SECRET\_KEY=your-secret-key-here
ENVIRONMENT=production
NEXT\_PUBLIC\_API\_URL=https://api.yourdomain.com
🤝 Contributing
Contributions are welcome! Please:

Fork the repository
Create a feature branch (git checkout -b feature/amazing-feature)
Commit changes (git commit -m 'Add amazing feature')
Push to branch (git push origin feature/amazing-feature)
Open a Pull Request
📄 License
This project is licensed under the MIT License — see LICENSE [blocked] file for details.

💡 Tips
Auto-generate API client: Use openapi-python-client or swagger-typescript-api to generate type-safe frontend code from
FastAPI OpenAPI spec
Database migrations: Always create migrations before schema changes (make migration name=add_user_table)
Email testing: Access Mailpit at http://localhost:8025 to see outgoing emails
API Documentation: Keep your Pydantic models well-documented — they auto-generate API docs
