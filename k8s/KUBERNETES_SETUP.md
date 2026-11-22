# Kubernetes deployment: Fresh Cart shopping agent

> Created using Anthropic Claude. Keep this as an internal draft until a human has reviewed and verified the content.

## 1. Overview

The Streamlit shopping agent (`src/app.py`, LangChain + Groq `openai/gpt-oss-120b`, SQLite `store.db`) runs on a local Kubernetes cluster as a containerized app.

| Item | Value |
|---|---|
| Cluster | Docker Desktop Kubernetes (context `docker-desktop`) |
| Nodes | `desktop-control-plane` (control plane), `desktop-worker` (worker), v1.36.1 |
| Image | `shopping-agent-shopping-agent:latest` (built locally by `docker compose build`) |
| Container port | 8501 (Streamlit) |
| Manifest | `k8s/deployment.yaml` |
| Replicas | 2 |

## 2. Changes made before deploying

| File | Change | Reason |
|---|---|---|
| `Dockerfile` | `streamlit run app.py` changed to `streamlit run src/app.py` | The app lives in `src/`; the old path would fail at container start. |
| `compose.yaml` | Host port `8501:8501` changed to `8502:8501` | Port 8501 was already used by a local `streamlit run`. |
| `.streamlit/config.toml`, `src/app.py` | New colourful theme and UI | Separate UI request; included in the image. |

## 3. Resources in `k8s/deployment.yaml`

1. **PersistentVolumeClaim `shopping-agent-data`**: 1Gi, ReadWriteOnce, mounted at `/app/resources` so `store.db` (and orders) survive pod restarts.
2. **Deployment `shopping-agent`**
   - 2 replicas, `Recreate` update strategy.
   - Image `shopping-agent-shopping-agent:latest`, `imagePullPolicy: IfNotPresent`.
   - Environment loaded from Secret `shopping-agent-env` through `envFrom`.
   - Readiness probe: HTTP GET `/_stcore/health` on 8501, initial delay 5s, period 10s.
   - Resources: requests 100m CPU / 256Mi memory, memory limit 1Gi.
3. **Service `shopping-agent`**: NodePort, port 80 to container 8501, nodePort 30080, `sessionAffinity: ClientIP` so a browser session stays on one pod (Streamlit keeps chat state per pod).

## 4. Secret handling

The Groq API key lives in `.env` and is not written into any manifest. The Secret was created directly from the file:

```bash
kubectl create secret generic shopping-agent-env --from-env-file=.env --dry-run=client -o yaml | kubectl apply -f -
```

`.env` is excluded from the image by `.dockerignore`. Per WBD policy, credentials should be managed through GICS; the local Secret above is for development only.

## 5. Deploy steps

```bash
docker compose build                                   # build the image
kubectl create secret generic shopping-agent-env --from-env-file=.env --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f k8s/deployment.yaml
kubectl rollout status deploy/shopping-agent
```

The local Docker Desktop cluster uses the local Docker image store, so no registry push was needed. On any other cluster the image must be pushed to a registry and the `image:` field updated.

## 6. Access

```bash
kubectl port-forward svc/shopping-agent 8503:80
# open http://localhost:8503
```

## 7. Verification performed

- `kubectl rollout status` reported the deployment successfully rolled out; both pods `1/1 Running` on `desktop-worker`.
- Via port-forward, `GET /_stcore/health` returned `ok`.
- **Not tested:** a chat message through the Kubernetes pods (Groq connectivity and order placement), and the NodePort from the host.

## 8. Health checking

```bash
kubectl get pods
kubectl get deploy shopping-agent
kubectl describe pod <pod-name>
kubectl logs deploy/shopping-agent
kubectl get endpoints shopping-agent
```

No liveness probe is configured yet. A proposed one (not applied):

```yaml
livenessProbe:
  httpGet: { path: /_stcore/health, port: 8501 }
  initialDelaySeconds: 20
  periodSeconds: 20
  failureThreshold: 3
```

## 9. Known limitations and risks

- **Shared SQLite volume:** both replicas mount one ReadWriteOnce volume. This works only because there is a single worker node. Concurrent writes can cause "database is locked" errors. For production use a server database (for example Postgres).
- **Database startup:** each pod runs `setup_db.py` at start. It uses `CREATE TABLE IF NOT EXISTS`, but the product-insert logic was not reviewed for duplicates. Verify the products table still has 32 rows.
- **Separate data:** the cluster database is independent of the local `resources/store.db` and the Docker Compose copy.
- **`:latest` tag:** rebuilding the image requires `kubectl rollout restart deploy/shopping-agent` to pick it up.
- **Not production-ready:** no Ingress/TLS, no autoscaling, no NetworkPolicy.

## 10. Teardown

```bash
kubectl delete -f k8s/deployment.yaml
kubectl delete secret shopping-agent-env
```

(Deleting the manifest also deletes the PVC and the cluster's `store.db`.)

## 11. Review checklist

- [ ] Confirm the Secret process meets credential policy (GICS).
- [ ] Verify an end-to-end chat and order in the cluster.
- [ ] Decide on a liveness probe and a production database.
- [ ] Share this document only with people authorized to see the project details.
