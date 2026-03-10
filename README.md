# Smart Auth API

Smart Auth API is a beginner-friendly but resume-grade backend project built with FastAPI, PostgreSQL, Redis, JWT, OAuth, Docker, and Nginx. It demonstrates the kind of architecture employers expect in 2026 for a modern backend service: typed API contracts, token-based authentication, OAuth login with Google and GitHub, explicit OAuth account linking, database migrations, rate limiting, Dockerized local development, and clear deployment guidance.

It now also includes structured JSON logging, Prometheus metrics, a Grafana API dashboard, and Kubernetes manifests so the project looks much closer to a modern production backend.

It also includes GitHub Actions workflows for CI and Docker image publishing so the repository can automatically test the app and publish a container image to GitHub Container Registry.

The internal code structure is also organized to stay scalable: API routes stay thin, business rules live in services, and database access is moving through repository-style classes so features can be changed without rewriting the whole app.

This repository is designed to be strong for learning and portfolio use, not to claim perfect production security. The current version adds safer OAuth linking rules, fail-closed auth throttling, a non-root container image, and Kubernetes network and runtime hardening so the security story is much more realistic for study and interview discussion.

## What You Will Learn

This project is structured so that studying and running it gives you hands-on experience with a set of backend engineering skills that come up repeatedly in interviews and real jobs.

### Authentication and security

- How to hash passwords correctly using Argon2 and why MD5 or SHA-256 alone are not safe for passwords
- How JWT access tokens work: what is inside them, why they are stateless, and what their expiry means
- How refresh token rotation works and why it is safer than a single long-lived token
- How OAuth2 works end-to-end: the authorization code flow, the `state` parameter, and why auto-linking by email is a security risk
- How Redis-backed rate limiting stops brute-force attacks and what fail-closed behavior means

### Backend architecture

- How to structure a FastAPI project with thin routes, a service layer, and a repository layer
- How Pydantic schemas enforce typed API contracts at the boundary between HTTP and Python
- How Alembic migrations keep database schema changes versioned and reproducible
- How SQLAlchemy models map Python classes to PostgreSQL tables
- How FastAPI dependency injection works for shared logic like authentication and database sessions

### Observability

- How Prometheus metrics are exposed from a FastAPI app and why counters and histograms are different
- How Grafana connects to Prometheus and turns raw metrics into readable panels
- How structured JSON logging with structlog makes log analysis easier than plain print statements
- How a live operator dashboard differs from static API documentation

### Infrastructure

- How Docker Compose coordinates multiple services and why the startup order matters
- How Nginx acts as a reverse proxy and what problems it solves in front of a Python app
- How Kubernetes Kustomize overlays separate base config from environment-specific patches
- How GitHub Actions CI runs tests and publishes Docker images automatically on every push

## Small Architecture Diagram

```mermaid
flowchart LR
  User[Browser or API Client] --> DockerPath[Nginx or Kubernetes Ingress]
  DockerPath --> API[FastAPI App]
  API --> PG[(PostgreSQL)]
  API --> Redis[(Redis)]
  API --> Metrics[/Metrics and Overview/]
  Metrics --> Prometheus[Prometheus]
  Prometheus --> Grafana[Grafana and Custom Dashboard]
  K8s[Kubernetes Overlay] --> DockerPath
```

Plain English:

- the client talks to one public entry point
- that entry point sends traffic to FastAPI
- FastAPI stores long-term data in PostgreSQL
- FastAPI stores fast temporary security data in Redis
- Prometheus and the dashboard help you see what the backend is doing while it is running

## Start The Project

This is the fastest way to run the project locally.

### Prerequisites

- Docker Desktop installed and running
- Python already installed on your machine if you want to run commands like tests or Alembic locally
- A `.env` file created from `.env.example`
- A private `local-access-notes.txt` file is available for your own passwords, callback URLs, and access notes, and it is ignored by git

### 1. Create the environment file

PowerShell:

```powershell
.\scripts\bootstrap-local-env.ps1
```

This generates a local `.env` with a strong `SECRET_KEY`, a non-default PostgreSQL password,
and a non-default Grafana admin password. Add your OAuth client credentials afterward if you
want Google or GitHub login to work locally.

Use `local-access-notes.txt` for the sensitive values and URLs you want to remember locally without committing them.

### 2. Start all services

```powershell
docker compose up --build
```

This starts:

- `api`: the FastAPI backend
- `db`: PostgreSQL database
- `redis`: Redis for rate limiting and temporary auth data
- `nginx`: reverse proxy in front of the API
- `prometheus`: metrics collection service
- `grafana`: dashboard for API traffic and latency

### 3. Run the database migration

Open a second terminal in the project folder and run:

```powershell
docker compose exec api alembic upgrade head
```

This creates the tables for users, OAuth accounts, and refresh tokens.

### 4. Open the running app

- Main URL through Nginx: http://localhost
- Direct API dashboard: http://localhost:8000
- Swagger docs: http://localhost/docs
- Health check: http://localhost/api/v1/health
- Metrics endpoint: http://localhost/metrics
- Prometheus UI: http://localhost:19090
- Grafana UI: http://localhost:13000

Note:

- On the first Docker build, the API container may take a short time to finish installing dependencies and starting up.
- During that short window, Nginx can return a temporary `502 Bad Gateway`. Refresh after a few seconds.
- Grafana login now uses the generated values from `.env` instead of a shared default admin password.
- Prometheus and Grafana host ports are configurable through `PROMETHEUS_PORT` and `GRAFANA_PORT` if those defaults are already in use on your machine.

## Security Posture

- Passwords are hashed with Argon2 through `pwdlib`.
- Refresh tokens are stored server-side and rotated on refresh.
- OAuth login no longer auto-links to an existing local account by email. Existing users must authenticate first and use the explicit OAuth link flow.
- Auth rate limiting can fail closed when Redis is unavailable.
- Proxy headers are only trusted when you explicitly enable `TRUST_PROXY_HEADERS` and define `TRUSTED_PROXY_CIDRS`.
- The Docker image now runs as a non-root user, and the Kubernetes deployment adds runtime security controls and a network policy.

## Troubleshooting

| Symptom                                                                         | Likely cause                                                                                  | What to do                                                                                                                                            |
| ------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `502 Bad Gateway` on `http://localhost` right after `docker compose up --build` | Nginx started before the API finished booting                                                 | Wait a few seconds, then refresh. Confirm with `docker compose ps` that `api` is healthy.                                                             |
| `api` container keeps restarting                                                | Missing or invalid values in `.env`                                                           | Re-run `./scripts/bootstrap-local-env.ps1`, then compare your `.env` against `.env.example`.                                                          |
| `PUBLIC_BACKEND_URL must use HTTPS in production`                               | `APP_ENV=production` is set while using a local `http://` URL                                 | For local work, use `APP_ENV=development`. Reserve production mode for real HTTPS deployments.                                                        |
| OAuth login returns provider or callback errors                                 | Google or GitHub client ID/secret is missing or callback URL does not match provider settings | Update the OAuth values in `.env` and make sure the provider callback exactly matches the URL documented in the app config.                           |
| OAuth login returns `409` for an existing email                                 | Existing local accounts must use the explicit link flow                                       | Sign in normally first, then start `/api/v1/auth/oauth/{provider}/link` so the provider account is linked intentionally.                              |
| Rate limiting or OAuth state behaves strangely                                  | Redis is not running or not reachable from the API                                            | Check `docker compose ps`, then inspect Redis with `docker compose logs redis`. Auth endpoints now fail closed when Redis is unavailable.             |
| All users appear to share one rate-limit bucket behind a reverse proxy          | Proxy headers are disabled or the proxy source IP is not in `TRUSTED_PROXY_CIDRS`             | Enable `TRUST_PROXY_HEADERS=true` only behind a trusted proxy and set `TRUSTED_PROXY_CIDRS` to the proxy network ranges that can reach the API.       |
| Login works but refresh/logout does not                                         | Database migrations were not applied                                                          | Run `docker compose exec api alembic upgrade head` and retry.                                                                                         |
| Prometheus or Grafana does not open                                             | Host port is already in use                                                                   | Change `PROMETHEUS_PORT` or `GRAFANA_PORT` in `.env`, then restart with `docker compose up -d --build`.                                               |
| Dashboard loads but looks empty                                                 | The overview endpoint is unavailable or the API is still starting                             | Open `http://localhost:8000/api/v1/system/overview` directly and confirm it returns JSON.                                                             |
| `configmap` or `secret` not found in Kubernetes                                 | Overlay-generated files were applied into the wrong namespace or not regenerated              | Re-run `./scripts/export-k8s-overlay-env.ps1 -Overlay local`, then apply the overlay again and confirm resources exist in the `smart-auth` namespace. |
| Kubernetes API pod never becomes ready                                          | Postgres, Redis, or config validation failed during startup                                   | Check `kubectl get pods -n smart-auth`, then `kubectl logs deployment/smart-auth-api -n smart-auth`.                                                  |

### Dashboard behavior

The root dashboard is now an operator screen, not a static landing page.

- It reads live backend state from `GET /api/v1/system/overview`.
- It shows request totals, error counts, latency, uptime, OAuth readiness, and route activity.
- Prometheus and Grafana links are driven by environment variables instead of hardcoded localhost values inside the frontend.

### 5. Explore the Control Room UI

Open `http://localhost:8000` in your browser. The dashboard has four tabs:

| Tab             | What it shows                                                                                                                                                                 |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Overview**    | Live service health, request totals, latency, error counts, OAuth readiness, and top routes — all pulled from the backend in real time                                        |
| **Auth Lab**    | Register form, login form, session and JWT token display, rate-limit progress bar, quick-fill buttons for seeded users, and an API tester that auto-injects your Bearer token |
| **Live Charts** | Chart.js time-series graphs for request rate, p95 latency, and error rate — all sourced live from Prometheus via a backend proxy                                              |
| **Monitoring**  | Embedded Grafana panels for the full observability dashboard                                                                                                                  |

#### Seeded test accounts

Three accounts are pre-seeded after running `alembic upgrade head`. Use them in the Auth Lab or via the API directly:

| Email               | Password       | Notes           |
| ------------------- | -------------- | --------------- |
| `admin@example.com` | `Admin1234!`   | Admin-role user |
| `alice@example.com` | `Alice1234!`   | Standard user   |
| `bob@example.com`   | `BobPass1234!` | Standard user   |

### 6. Test the API via Swagger

Open `http://localhost/docs` to use the interactive Swagger UI, or call endpoints directly:

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`

## Example API Flow

These examples are the easiest way to understand what the project actually does.

### 1. Register a user

Request:

```json
{
  "email": "demo@example.com",
  "full_name": "Demo User",
  "password": "StrongPass123"
}
```

Call:

- Method: `POST`
- URL: `http://localhost/api/v1/auth/register`

What it does:

- Creates the user in PostgreSQL
- Hashes the password before storing it
- Returns an access token and refresh token

### 2. Log in

Request:

```json
{
  "email": "demo@example.com",
  "password": "StrongPass123"
}
```

Call:

- Method: `POST`
- URL: `http://localhost/api/v1/auth/login`

What it does:

- Checks the email and password
- Creates a short-lived access token
- Creates a longer-lived refresh token

### 3. Call a protected route

Call:

- Method: `GET`
- URL: `http://localhost/api/v1/auth/me`
- Header: `Authorization: Bearer YOUR_ACCESS_TOKEN`

What it does:

- Verifies the JWT access token
- Reads the matching user from PostgreSQL
- Returns the logged-in user's profile

### 4. Refresh the access token

Request:

```json
{
  "refresh_token": "YOUR_REFRESH_TOKEN"
}
```

Call:

- Method: `POST`
- URL: `http://localhost/api/v1/auth/refresh`

What it does:

- Validates the refresh token
- Revokes the previous refresh token record
- Returns a new access token and a new refresh token

### 5. Log out

Request:

```json
{
  "refresh_token": "YOUR_REFRESH_TOKEN"
}
```

Call:

- Method: `POST`
- URL: `http://localhost/api/v1/auth/logout`

What it does:

- Marks the refresh token as revoked in PostgreSQL
- Prevents that refresh token from being reused later

### 6. Start Google or GitHub login

Call one of these:

- `GET http://localhost/api/v1/auth/oauth/google/login`
- `GET http://localhost/api/v1/auth/oauth/github/login`

What it does:

- Creates a secure temporary `state` value in Redis
- Returns a provider authorization URL
- Sends the user to Google or GitHub for login approval

### 7. OAuth callback

After the provider redirects back, the backend callback endpoint:

- validates the temporary `state` from Redis
- exchanges the provider code for user identity data
- signs in an already linked OAuth user or creates a new user when the email is not already in use
- returns JWT tokens for your API

### 8. Link Google or GitHub to an existing account

Call one of these after you are already authenticated with a bearer token:

- `GET http://localhost/api/v1/auth/oauth/google/link`
- `GET http://localhost/api/v1/auth/oauth/github/link`

What it does:

- creates a short-lived state value tied to your current user ID
- redirects you to the provider using a dedicated link callback URL
- links the provider account only to the authenticated local user that started the flow

## Start Without Docker

Use this only if you already have PostgreSQL and Redis running yourself.

```powershell
pip install -e .[dev]
alembic upgrade head
uvicorn app.main:app --reload
```

If you use this mode, make sure `.env` points to your own PostgreSQL and Redis instances.

## Why This Project Is Strong For A Resume

- Uses a real backend stack instead of a tutorial-only toy app.
- Shows both classic email/password auth and OAuth login.
- Uses PostgreSQL for durable data and Redis for API protection.
- Includes JWT access and refresh token flow with rotation.
- Ships with Docker Compose and Nginx for realistic local deployment.
- Keeps the code intentionally readable so you can explain it in interviews.

## Key Concepts

These are the core ideas behind the project. Understanding them is more useful than memorising the code.

**JWT (JSON Web Token)**
A signed string the server gives to the client after login. The client sends it back on every request. The server verifies the signature without needing a database lookup. It expires quickly (15 minutes here) so a stolen token becomes useless fast.

**Refresh token**
A longer-lived token stored in PostgreSQL. When the access token expires, the client sends the refresh token to get a new access token. The old refresh token is immediately invalidated (rotated), so if it gets stolen, the attacker only has one use before the legitimate user's next refresh locks them out.

**OAuth2 authorization code flow**
Instead of giving this app your Google or GitHub password, you approve access directly on the provider's site. The provider sends a short-lived code back to this app. The app exchanges that code for your profile details server-side. A `state` parameter stored in Redis prevents cross-site request forgery during the redirect.

**Rate limiting**
Redis counts how many auth requests a given IP has made in the last 60 seconds. Once the count exceeds the limit the request is rejected immediately without hitting the database. If Redis is down, the app refuses all auth requests (fail-closed) rather than silently removing the protection.

**Argon2 password hashing**
Argon2 is designed to be slow and memory-intensive, which makes brute-force attacks expensive even if the hashed passwords are stolen. bcrypt is also common but Argon2 is the current winner of the Password Hashing Competition and is the recommended choice for new projects.

**Repository pattern**
Database queries live in dedicated repository classes rather than scattered across route handlers. This means swapping the database implementation, adding caching, or writing tests with a fake database requires changing one file instead of many.

**Prometheus metrics**
The app increments counters and records timing histograms on every request. Prometheus scrapes these numbers on a timer. Grafana queries Prometheus and draws charts. This is the standard observability stack for container-based backends.

## Tech Stack

- FastAPI for the API layer
- PostgreSQL for users, OAuth links, and refresh tokens
- Redis for rate limiting and OAuth state storage
- Nginx as a reverse proxy
- JWT for access and refresh tokens
- Google and GitHub OAuth login support
- SQLAlchemy and Alembic for data models and migrations
- Structlog and JSON logs for modern backend logging
- Prometheus for API metrics
- Grafana for dashboards
- Kubernetes manifests for container orchestration

## Why These Pieces Exist

This section explains the major tools in plain English: what problem each one solves here, and what would happen if you removed it.

### Docker

Docker makes the app, PostgreSQL, Redis, Nginx, Prometheus, and Grafana run in predictable containers instead of depending on whatever happens to be installed on your machine.

Example:

- without Docker, one machine might use PostgreSQL 16, another might use PostgreSQL 14, and another might not have Redis installed at all
- with Docker, everyone runs the same services the same way

If you do not use Docker here:

- setup becomes slower and more fragile
- "it works on my machine" problems become much more common
- onboarding and demo setup become harder

### Kubernetes

Kubernetes solves the next problem after Docker: running containers reliably in a cluster instead of just on one local machine.

Example:

- Docker says, "run this API container"
- Kubernetes says, "keep one or more API containers alive, restart them if they die, wait for Postgres to be ready, expose the service, and keep configuration separate from the image"

If you do not use Kubernetes here:

- the project still works locally with Docker Compose
- but you do not show cluster deployment skills like health probes, rolling updates, service discovery, and ingress routing

### PostgreSQL

PostgreSQL stores data that must survive restarts: users, OAuth links, and refresh tokens.

Example:

- if a user signs up today, that account still needs to exist tomorrow

If you do not use a real database here:

- accounts disappear when the app restarts
- refresh token revocation becomes unreliable
- the project stops looking like a serious backend

### Redis

Redis stores fast temporary data. In this project it is used for rate limiting and short-lived OAuth state.

Example:

- when a user keeps hitting login over and over, Redis can quickly count those attempts and slow them down
- when OAuth starts, Redis stores a short-lived `state` value to protect the callback flow

If you do not use Redis here:

- rate limiting becomes much harder or slower
- OAuth state handling becomes weaker
- you would probably push temporary security data into PostgreSQL even though it is not the best fit

### JWT access tokens and refresh tokens

JWT access tokens let the API verify who the user is on each request without storing a server-side session for every logged-in user. Refresh tokens let users stay logged in without making access tokens long-lived.

Example:

- the access token might live for 15 minutes
- the refresh token can be exchanged for a new access token later

If you do not use this pattern here:

- either users log in too often
- or you keep long-lived access tokens, which is worse for security
- or you move back to server-side sessions, which changes the architecture completely

### Nginx

Nginx is the reverse proxy in front of the API for the Docker setup.

Example:

- the browser talks to Nginx on port 80
- Nginx forwards the request to the FastAPI app on port 8000

Why that matters:

- this is closer to how real deployments are usually structured
- it gives you one clean public entry point

If you do not use Nginx here:

- the project still works
- but you lose the reverse-proxy layer that many production systems rely on for routing and traffic control

### Alembic migrations

Alembic keeps database schema changes versioned.

Example:

- instead of manually creating tables every time, you run one command and the schema moves to the right version

If you do not use migrations here:

- database setup becomes manual
- changes become harder to track
- deployments become riskier because schema drift is easier to introduce

### Prometheus and the dashboard

Prometheus collects metrics. The custom dashboard and Grafana turn those metrics and service state into something readable.

Example:

- instead of only knowing "the server is up," you can also see request volume, latency, exceptions, OAuth readiness, and hot routes

If you do not use them here:

- debugging becomes slower
- performance problems stay hidden longer
- the project feels more like a coding exercise than an operational backend

## Stack In One Picture

You can think of the project like this:

- FastAPI handles the API logic
- PostgreSQL keeps durable identity data
- Redis handles fast temporary security data
- JWT handles stateless API authentication
- Docker makes local setup repeatable
- Kubernetes makes cluster deployment repeatable
- the dashboard makes runtime behavior visible

## Docker Check

I tested the project against Docker Compose on this machine.

What was true:

- Docker Compose was already installed and working.
- The project did not start automatically at first because `.env` was missing.
- After adding `.env`, the stack built correctly.
- The next runtime issue was a config parsing bug for `CORS_ORIGINS`, which has now been fixed.

What this means:

- Yes, the project is compatible with an existing Docker setup.
- The stack should work with your current Docker installation as long as Docker Desktop is running.
- Google and GitHub login still require real OAuth credentials before those specific endpoints can complete the external login flow.
- The observability stack also runs in Docker now, so Prometheus and Grafana should come up with the same `docker compose up --build` command.

## Docker Gotchas

- The first build can take a while because Python dependencies and images need to download.
- If `.env` changes database or Grafana credentials after volumes already exist, the running containers may need those credentials updated too. Changing `.env` alone is not always enough because the volume can preserve old state.
- A temporary `502 Bad Gateway` from Nginx usually means the API container is still starting.
- Prometheus and Grafana ports can conflict with tools already running on your machine, which is why they are configurable in `.env`.

## Architecture Summary

The project is organized around a few simple ideas:

- `app/api`: FastAPI routes and request dependencies
- `app/core`: settings, security, and rate limiting
- `app/middleware`: request logging, request IDs, and metrics collection
- `app/db`: database engine and metadata wiring
- `app/models`: SQLAlchemy models
- `app/repositories`: focused database access classes for users, refresh tokens, and OAuth links
- `app/schemas`: Pydantic request and response models
- `app/services`: business logic for auth and OAuth
- `alembic`: database migrations
- `nginx`: reverse proxy configuration
- `prometheus`: scrape configuration for metrics collection
- `grafana`: dashboard provisioning and API monitoring panels
- `k8s`: Kubernetes manifests for container deployment

## Authentication Flow

### Email and password

1. A user registers with email, full name, and password.
2. The password is hashed with Argon2 via `pwdlib`.
3. The API returns an access token and a refresh token.
4. Refresh tokens are stored in PostgreSQL so they can be rotated and revoked.

### Google and GitHub login

1. The client requests `/api/v1/auth/oauth/{provider}/login`.
2. The API generates a provider URL and stores a secure `state` value in Redis.
3. The provider redirects back to `/api/v1/auth/oauth/{provider}/callback`.
4. The backend exchanges the code for provider user info, then either signs in an already linked user or creates a new one when that email is not already claimed.
5. If the email already belongs to a local account, the user must authenticate first and use `/api/v1/auth/oauth/{provider}/link`.

### Rate limiting

- Auth endpoints are protected with Redis-backed per-IP rate limiting.
- If Redis is temporarily unavailable, auth endpoints can fail closed instead of silently dropping brute-force protection.
- `X-Forwarded-For` is only trusted when the caller is a trusted reverse proxy from `TRUSTED_PROXY_CIDRS`.

## Important Environment Variables

- `SECRET_KEY`: signs JWT tokens, so it must be long and secret in production
- `LOG_LEVEL`: controls how detailed the backend logs should be
- `DATABASE_URL`: tells the API how to connect to PostgreSQL
- `REDIS_URL`: tells the API how to connect to Redis
- `PUBLIC_BACKEND_URL`: used to build OAuth callback URLs
- `CORS_ORIGINS`: controls which frontend origins are allowed to call the API from a browser
- `RATE_LIMIT_FAIL_CLOSED`: decides whether auth endpoints return `503` when Redis throttling is unavailable
- `TRUST_PROXY_HEADERS` and `TRUSTED_PROXY_CIDRS`: control when forwarded client IP headers should be trusted
- `GRAFANA_ADMIN_USER` and `GRAFANA_ADMIN_PASSWORD`: control local Grafana login credentials
- `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`: enable Google login
- `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET`: enable GitHub login

## Monitoring And Dashboard

### What is already included

- `/metrics` exposes Prometheus metrics from the FastAPI app
- Prometheus scrapes the API automatically
- Grafana auto-loads a dashboard called `Smart Auth API Observability`

### What the dashboard shows

- request rate
- unhandled exceptions
- p95 response time by route
- request breakdown by method, route, and status code

### Why this matters

These tools make the project feel more like a real production backend. Instead of only seeing whether the API is up, you can see how busy it is, which routes are slow, and whether errors are increasing.

### What problem the custom dashboard solves

Swagger tells you how to call the API. The dashboard tells you what the backend is doing right now.

Example:

- Swagger helps you test `POST /login`
- the dashboard helps you notice that login traffic is spiking or that the API has started throwing errors

If you remove the dashboard:

- the backend still works
- but it becomes harder to understand its live behavior at a glance

## GitHub Actions

The repository includes two GitHub Actions workflows:

- `.github/workflows/ci.yml`
- `.github/workflows/publish-image.yml`

### What it does

- runs tests on Python 3.12 and 3.14
- installs the project with development dependencies
- builds the Docker image to catch container-level breakage early
- publishes a Docker image to GitHub Container Registry on pushes to `main` or `master` and on version tags like `v1.0.0`

### Why this matters

This makes the project look more production-ready on GitHub. It also helps prevent broken commits from being merged without at least basic validation.

### Published image format

The publish workflow pushes images in this shape:

- `ghcr.io/YOUR_GITHUB_USERNAME/smart-auth-api:latest`
- `ghcr.io/YOUR_GITHUB_USERNAME/smart-auth-api:sha-...`
- `ghcr.io/YOUR_GITHUB_USERNAME/smart-auth-api:v1.0.0`

If you want Kubernetes to use the published image, point the production overlay at your real GHCR image before applying it.

## Kubernetes

The Kubernetes setup now uses a real Kustomize structure instead of isolated YAML files.

### What Kubernetes is solving here

Docker is enough to run everything on one machine. Kubernetes is used when you want the platform to manage the containers for you.

In this project, Kubernetes handles:

- keeping the API running
- starting Postgres and Redis as in-cluster services
- creating persistent storage
- separating config and secrets from the image
- exposing the API through an ingress
- running the migration job in the cluster

### Folder layout

- `k8s/base`: reusable resources shared by every environment
- `k8s/overlays/local`: local cluster settings for Minikube, kind, or Docker Desktop Kubernetes
- `k8s/overlays/production`: production-specific settings
- `scripts/export-k8s-overlay-env.ps1`: generates overlay config from your current `.env`

### Local Kubernetes setup

If you want to run this project on Minikube locally:

1. Start Minikube.
2. Build the local image.
3. Load the image into Minikube.
4. Export the local overlay env files.
5. Apply the local overlay.

Commands:

```powershell
minikube start --driver=docker
docker build -t smart-auth-api:latest .
minikube image load smart-auth-api:latest
.\scripts\export-k8s-overlay-env.ps1 -Overlay local
kubectl apply -k k8s/overlays/local
```

### Local Kubernetes gotchas

- The local overlay intentionally uses `APP_ENV=development`. This is not a mistake. It is needed because the production validator requires an `https://` public URL, while local Minikube usually uses `http://` during development.
- Generated `ConfigMap` and `Secret` resources must be in the same namespace as the workloads. If they land in `default`, the pods will fail with `configmap not found` or `secret not found` errors.
- If you rebuild the app image, load it into Minikube again before restarting the deployment.
- If the migration job failed because of bad config, deleting the old job and re-applying the overlay is the cleanest fix.
- Ingress on Minikube usually needs the ingress addon enabled. In many setups you also need `minikube tunnel` before the host becomes reachable from your browser.
- If ingress is not ready yet, `kubectl port-forward svc/smart-auth-api 8080:80 -n smart-auth` is the fastest fallback.

### Production Kubernetes flow

1. Copy `k8s/overlays/production/config.env.example` to `k8s/overlays/production/config.env`.
2. Copy `k8s/overlays/production/secrets.env.example` to `k8s/overlays/production/secrets.env`.
3. Set your real image, real domain, and real secrets.
4. Apply with `kubectl apply -k k8s/overlays/production`.

### Why the Kubernetes setup is useful now

- it was validated on Minikube, not just written as placeholder YAML
- the local overlay can actually boot the app, run the migration, and expose the service
- it documents the real failure modes we hit while making it work

Detailed Kubernetes commands and cluster notes are in `k8s/README.md`.

## Architecture Choices

### Repository layer

The repository layer keeps SQL queries out of the API routes and reduces duplication inside services. This matters because when the project grows, database logic can change in one place instead of being scattered across many files.

### Thin routes and service layer

The API routes mostly validate input and call services. The services hold the real auth logic. This makes the code easier to test, easier to extend, and easier to replace later if you add more auth methods or admin workflows.

### Provider-based OAuth structure

The OAuth code is organized so each provider can have its own fetch logic and config. That makes it much easier to add another login provider later, such as Microsoft or Discord, without rewriting the whole OAuth flow.

## OAuth Setup

### Google OAuth

Create credentials in Google Cloud Console and add this callback URL:

```text
http://localhost/api/v1/auth/oauth/google/callback
```

### GitHub OAuth

Create an OAuth app in GitHub Developer Settings and add this callback URL:

```text
http://localhost/api/v1/auth/oauth/github/callback
```

## Core Endpoints

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `GET /api/v1/auth/oauth/google/login`
- `GET /api/v1/auth/oauth/google/callback`
- `GET /api/v1/auth/oauth/github/login`
- `GET /api/v1/auth/oauth/github/callback`
- `GET /api/v1/health`

## Free Hosting Strategy For 2026

For a real public deployment, use this split:

- FastAPI app: Render, Railway, or Fly.io
- PostgreSQL: Neon or Supabase Postgres free tier
- Redis: Upstash free tier
- Nginx: optional in production if the platform already handles ingress

This keeps your GitHub repo professional while still being affordable.

## Deployment Idea

For a clean real deployment, use this pattern:

1. Push the code to GitHub.
2. Deploy the FastAPI app to Render, Railway, or Fly.io.
3. Use Neon or Supabase for PostgreSQL.
4. Use Upstash for Redis.
5. Add the hosted environment variables in the deployment platform.
6. Update `PUBLIC_BACKEND_URL` to your real domain.

## Suggested GitHub Repo Talking Points

Use these ideas in your README summary, LinkedIn post, or interview explanation:

- Built a production-style authentication API using FastAPI, PostgreSQL, Redis, JWT, and OAuth.
- Implemented refresh token rotation and revocation.
- Protected sensitive endpoints with Redis-backed rate limiting.
- Dockerized the stack with Nginx reverse proxy for realistic local deployment.
- Designed the codebase with modular services, schemas, and migration support.
- Structured the backend with thin routes, service logic, and repository-style data access for easier long-term maintenance.
- Added structured JSON logging, Prometheus metrics, and a Grafana dashboard for API observability.
- Added Kubernetes manifests for container-based deployment.
- Added GitHub Actions CI to automatically run tests and validate Docker builds.
- Added GitHub Actions publishing to push Docker images to GitHub Container Registry.

## Interview Questions This Project Prepares You For

These are real questions that come up in backend and security-focused interviews. This project gives you a concrete, working answer to each one.

**"How does JWT authentication work?"**
Explain the access token / refresh token split, why JWTs are stateless, how the signature is verified, and why short expiry matters. Point to `app/core/security.py` and `app/services/auth_service.py`.

**"How do you prevent brute-force login attacks?"**
Explain the Redis-backed sliding-window rate limiter, fail-closed behaviour when Redis is unavailable, and per-IP bucketing via trusted proxy headers. Point to `app/core/rate_limiter.py`.

**"What is OAuth2 and how does the authorization code flow work?"**
Walk through the login → redirect → callback → token exchange sequence. Explain the `state` parameter and why auto-linking by email is a security risk. Point to `app/services/oauth_service.py`.

**"Why do you store refresh tokens in the database if JWTs are stateless?"**
JWTs alone cannot be revoked before expiry. Storing refresh tokens in PostgreSQL allows logout and rotation. The access token stays stateless; only the longer-lived refresh token needs server-side state.

**"How would you structure a FastAPI project for a team?"**
Describe the thin-route → service layer → repository layer pattern. Explain why business logic should not live in route handlers and why database queries should not live in services directly.

**"How do you observe a running backend service?"**
Explain Prometheus counters and histograms, Grafana panels, structured JSON logs, and time-series alerting. Contrast this with print-statement debugging or checking if the server is simply `up`.

**"What is the difference between Docker Compose and Kubernetes?"**
Docker Compose coordinates services on one machine. Kubernetes keeps containers alive across a cluster, handles rolling updates, separates config from images, and provides service discovery at scale.

**"How do you handle database schema changes safely?"**
Alembic migration files version every schema change. Rolling back is a single command. Changes are tracked in the repository so every environment applies the same sequence.

## Planned Features

These are the next meaningful additions to this project. Each one extends the authentication foundation that already exists without needing to replace any part of the current stack.

### 1. Role-Based Access Control (RBAC)

Users will be assigned roles such as `admin`, `editor`, and `viewer`. Each role will carry a set of named permissions. Protected routes will check permissions rather than only checking whether the user is logged in.

What this adds:

- a `roles` and `permissions` table in PostgreSQL
- a `require_permission("users:delete")` FastAPI dependency that can be applied to any route
- admin-only endpoints for managing users and roles
- a natural extension to the existing `User` model and `deps.py` injection pattern

Why it matters:

- Authentication answers "who are you?" but authorization answers "what are you allowed to do?" — this feature completes the access control story.
- Almost every real multi-user system needs this. It is one of the most commonly asked-about topics in backend interviews.

### 2. Audit Log

Every security-significant action — login, failed login, logout, token refresh, password change, OAuth link — will be written to an `audit_events` table with the timestamp, user ID, IP address, user agent, and outcome.

What this adds:

- an `AuditEvent` SQLAlchemy model and migration
- a background task writer so the audit write does not slow down the main request
- a `/api/v1/admin/audit-log` endpoint paginated by user or time range

Why it matters:

- Audit logs are required for SOC 2 and GDPR compliance in production systems.
- They make the security story of the project much more complete.
- They turn abstracted auth events into something visible and queryable, which is useful for a thesis demonstration.

### 3. API Key Management

Users or service accounts will be able to generate named API keys with defined scopes and optional expiry dates. Callers authenticate using `Authorization: Bearer <api-key>` instead of a short-lived JWT.

What this adds:

- an `api_keys` table that stores only the key hash, never the raw key
- a key generation endpoint that shows the raw key exactly once on creation
- per-key scope enforcement using the same permission dependency used by RBAC
- per-key request tracking visible in Prometheus metrics

Why it matters:

- This is how Stripe, GitHub, and AWS handle machine-to-machine authentication. It is a completely separate auth flow from user JWTs and teaches a distinct set of skills.
- It makes the project useful as a model for service-to-service auth, not only user login.

### 4. Two-Factor Authentication (TOTP)

Users who enable 2FA will be required to submit a 6-digit time-based one-time password from an authenticator app as a second step after entering their email and password. The implementation follows RFC 6238, the same standard used by Google, GitHub, and most major services.

What this adds:

- a `totp_secret` column on the user table
- `/api/v1/auth/2fa/setup` to generate a QR code and secret
- `/api/v1/auth/2fa/verify` to confirm setup and enable 2FA
- a two-step login flow where step one returns a short-lived challenge token stored in Redis and step two validates the TOTP code before issuing real JWT tokens

Why it matters:

- 2FA is one of the most effective controls against credential-based attacks.
- Implementing it correctly requires understanding partial sessions, challenge state, and time-window tolerance, which makes it a strong learning topic.

### 5. Webhook Delivery

When notable events occur — `user.registered`, `user.login`, `password.reset`, `api_key.created` — the system will POST a signed JSON payload to URLs that admins or users have registered.

What this adds:

- a `webhooks` table of registered endpoint URLs and their event subscriptions
- a Redis-backed delivery queue with exponential backoff retries on failure
- `X-Signature-256` header signing using HMAC so receivers can verify the payload is genuine
- a delivery log showing recent attempts and outcomes

Why it matters:

- Webhooks are the integration layer of nearly every SaaS product.
- Reliable delivery with retries and signature verification is a distinct engineering skill from standard REST API design.
- It makes the project useful as a model for event-driven system integration.

---

### Planned implementation order

| Step | Feature                   | Rationale                                                                    |
| ---- | ------------------------- | ---------------------------------------------------------------------------- |
| 1    | RBAC                      | Completes the access control story; needed before admin endpoints make sense |
| 2    | Audit Log                 | Builds on RBAC events; adds compliance value immediately                     |
| 3    | API Key Management        | Introduces machine-to-machine auth as a separate flow from user JWTs         |
| 4    | Two-Factor Authentication | Strengthens the user login flow with a second factor                         |
| 5    | Webhook Delivery          | Adds event-driven integration on top of the complete auth foundation         |

---

## Other Improvements

- Add email verification so users must prove they own the email address before the account is activated.
- Add password reset flow so forgotten passwords can be changed securely via a signed reset link.
- Add account lockout rules for repeated failed login attempts beyond the current rate-limit window.
- Add integration tests that run against a temporary PostgreSQL and Redis stack.
- Add OpenTelemetry tracing and Tempo or Jaeger for distributed tracing across service boundaries.
- Add Loki or another centralized log store so Grafana can explore structured logs alongside metrics.
- Add email provider support for system emails such as verification links and password reset.
- Add user profile update endpoints and a secure account deletion flow.
- Add a frontend client example in React or Next.js to demonstrate the full end-to-end login experience.

## Docker Cleanup

If you build often, Docker can keep old unused image layers and cache around.

Useful cleanup commands:

```powershell
docker image prune -f
docker builder prune -f
```

There is also an automated cleanup script in `scripts/cleanup-docker.ps1`.

### Safe cleanup

```powershell
.\scripts\cleanup-docker.ps1
```

This removes:

- stopped containers
- dangling images
- unused volumes
- old build cache

### More aggressive cleanup

```powershell
.\scripts\cleanup-docker.ps1 -Aggressive -IncludeNetworks
```

This also removes:

- all unused images, not just dangling ones
- unused Docker networks

What they do:

- `docker image prune -f` removes dangling unused images
- `docker builder prune -f` removes old build cache layers
- `docker volume prune -f` removes volumes not used by any container
- `docker container prune -f` removes stopped containers

The cleanup script is safe by default because it does not stop running containers or remove volumes attached to active containers.
