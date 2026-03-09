# Kubernetes Deployment

This project now uses Kustomize so Kubernetes configuration is actually reusable instead of being a pile of one-off YAML files.

## Structure

- `k8s/base`: reusable manifests for API, Postgres, Redis, ingress, and migration job
- `k8s/overlays/local`: local cluster overlay for `kind`, `minikube`, or Docker Desktop Kubernetes
- `k8s/overlays/production`: production overlay with separate environment files and replica counts

## Local cluster flow

### 1. Build the image

```powershell
docker build -t smart-auth-api:latest .
```

### 2. Load the image into your cluster if needed

For `kind`:

```powershell
kind load docker-image smart-auth-api:latest
```

For Docker Desktop Kubernetes, you usually do not need an extra load step if Docker built the image locally.

### 3. Generate overlay env files from `.env`

```powershell
.\scripts\export-k8s-overlay-env.ps1 -Overlay local
```

This writes:

- `k8s/overlays/local/config.env`
- `k8s/overlays/local/secrets.env`

It converts the local Docker-style `.env` into cluster values such as:

- `DATABASE_URL=postgresql+asyncpg://...@postgres:5432/smart_auth`
- `REDIS_URL=redis://redis:6379/0`
- `PUBLIC_BACKEND_URL=http://smart-auth.localtest.me`
- `APP_ENV=development` for the local cluster overlay so local HTTP ingress works without production HTTPS requirements

### 4. Apply the local overlay

```powershell
kubectl apply -k k8s/overlays/local
```

### 5. Reach the app

If you have an ingress controller installed, open:

```text
http://smart-auth.localtest.me
```

If you do not have an ingress controller yet, use port-forwarding:

```powershell
kubectl -n smart-auth port-forward svc/smart-auth-api 8080:80
```

Then open:

```text
http://localhost:8080
```

## Local gotchas

- The local overlay exports `APP_ENV=development` on purpose. The app's production validator requires an `https://` public URL, and local Minikube access is usually `http://`.
- If the pods say `configmap not found` or `secret not found`, check that the generated resources were created in `smart-auth`, not in `default`.
- If you rebuild the API image, run `minikube image load smart-auth-api:latest` again before restarting the deployment.
- If ingress is enabled but the host still does not open, run `minikube tunnel` in a separate terminal.
- If ingress is still not convenient, use `kubectl -n smart-auth port-forward svc/smart-auth-api 8080:80`.
- If the migration job failed because of an earlier config mistake, delete it and re-apply the overlay so Kubernetes creates a fresh job.

## Troubleshooting

| Symptom                                                 | Likely cause                                                               | What to do                                                                                                                                          |
| ------------------------------------------------------- | -------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ImagePullBackOff` for `smart-auth-api`                 | The local image was rebuilt but not loaded into Minikube                   | Run `docker build -t smart-auth-api:latest .`, then `minikube image load smart-auth-api:latest`, then restart the deployment.                       |
| `configmap not found` or `secret not found`             | Overlay env files were not regenerated or landed in the wrong namespace    | Re-run `./scripts/export-k8s-overlay-env.ps1 -Overlay local`, then `kubectl apply -k k8s/overlays/local` and verify resources in `smart-auth`.      |
| API pod starts then exits with config validation errors | Local overlay is missing `APP_ENV=development` or has invalid URLs/secrets | Regenerate the overlay env files from the current `.env`, then inspect `kubectl logs deployment/smart-auth-api -n smart-auth`.                      |
| Ingress host does not open even though pods are running | Ingress addon or local routing is not fully ready                          | Check `kubectl get ingress -n smart-auth`, run `minikube tunnel` if needed, or use `kubectl -n smart-auth port-forward svc/smart-auth-api 8080:80`. |
| Migration job failed and the API never becomes healthy  | Database was unavailable or config was wrong during the first job run      | Fix the underlying issue, delete the failed job or pod, and re-apply the overlay so Kubernetes creates a new migration job.                         |

## Why this setup exists

### Why Docker first

Docker is the easiest way to make the local stack consistent. It solves the "different machine, different setup" problem.

Without Docker:

- you would need to install Postgres, Redis, and other tools manually
- version mismatches would be more common
- onboarding would be slower

### Why Kubernetes after Docker

Kubernetes solves a different problem. It is not mainly about packaging the app. It is about managing the packaged app in a cluster.

In this project, Kubernetes handles:

- service discovery between API, Postgres, and Redis
- restart behavior if a container fails
- health checks
- ingress routing
- separation of config and secrets from the image
- running migrations inside the cluster

Without Kubernetes:

- local development is still fine with Docker Compose
- but you lose the cluster deployment part of the project
- you also lose proof that the app can survive beyond one-machine development

## Production flow

1. Copy `k8s/overlays/production/config.env.example` to `k8s/overlays/production/config.env`.
2. Copy `k8s/overlays/production/secrets.env.example` to `k8s/overlays/production/secrets.env`.
3. Set a real image reference with `kustomize edit set image` or by editing the overlay.
4. Set your real domain in the ingress patch.
5. Apply with `kubectl apply -k k8s/overlays/production`.

## Why this is better

- Base manifests stay reusable across environments.
- Secrets are generated from env files instead of being hardcoded in YAML.
- The local overlay is runnable with your current `.env` and local Docker image.
- Postgres and Redis have health checks and persistent storage.
- The API waits for dependencies before starting.
- The migration job waits for Postgres and cleans itself up after completion.
