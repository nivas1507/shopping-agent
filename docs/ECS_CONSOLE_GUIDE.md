# Deploy Fresh Cart to AWS ECS Fargate: console guide

> Created using Anthropic Claude. Keep this as an internal draft until a human has reviewed and verified the content. Share it only with people authorized to see this project's details.

## 0. Overview

You will run the Streamlit shopping agent as **one Fargate task** behind an **Application Load Balancer (ALB)**. The SQLite database lives on the task's own temporary disk (**no persistence**), so products and reviews are recreated on every start and any orders are lost whenever the task restarts or is redeployed. The Groq API key comes from **Secrets Manager**.

```
Browser --HTTP:80--> ALB (public subnets, sticky sessions)
                       |
                       v  :8501
              Fargate task (private subnets)
               |- image from ECR
               |- GROQ_API_KEY from Secrets Manager
               |- logs to CloudWatch
               `- store.db on the task's ephemeral disk (recreated at each start)
```

### Values used in this guide (verified against the account)

| Item | Value |
|---|---|
| Account / region | `763679488809` / `us-east-1` |
| ECR image | `763679488809.dkr.ecr.us-east-1.amazonaws.com/shopping-agent:f04d8225140967914877b36feddc08ab8f6ecb26` (also tagged `latest`) |
| VPC | `vpc-0c6634cdfa0eab96f` (10.56.140.0/23). There is **no default VPC**; always pick this one. |
| Public subnets (for the ALB) | `subnet-0a71f4a306cf54df8` (1a), `subnet-00c75277a07dd10a5` (1b), `subnet-030de4e5b2d4a7e80` (1c) |
| Private subnets (for the task) | `subnet-021e4e39fdba421aa` (1a), `subnet-07bd1a295b7666fc5` (1b), `subnet-01e9e3fef1a5565ad` (1c) |
| Do not use | the `...-transit` subnets |
| Task execution role | `ecsTaskExecutionRole` (already exists) |
| Name prefix | `shopping-agent-` (this is a shared dev account; keep names unique) |

Private subnets reach the internet through a NAT gateway, which the task needs to pull from ECR and to call the Groq API. Public subnets route to an internet gateway, which the ALB needs.

**Important rules**
- Run exactly **1 task**. Each task has its own separate database, so a second task would show different orders, and Streamlit chat state lives inside the task.
- **No persistence:** orders are deleted whenever the task stops, crashes or is redeployed. This setup is for demos only.
- Use the **commit-SHA image tag**, not `latest`, so each deployment is traceable.
- Costs accrue while the task and ALB exist. Clean up (section 14) when finished.

**Prerequisites:** you are signed in to the AWS console in account `763679488809`, region **N. Virginia (us-east-1)**, and the image exists in ECR (ECR → Repositories → `shopping-agent`).

---

## 1. Create the security groups

EC2 → **Security Groups** → **Create security group**. Use VPC `vpc-0c6634cdfa0eab96f` for both. Create them in this order.

| # | Name | Inbound rule | Outbound |
|---|---|---|---|
| 1 | `shopping-agent-alb-sg` | HTTP, TCP 80, source = your allowed CIDR (for example your corporate range). Avoid `0.0.0.0/0` in a shared account unless you need public access. | default (all) |
| 2 | `shopping-agent-task-sg` | Custom TCP 8501, source = security group `shopping-agent-alb-sg` | default (all) |

**Expected result:** two groups listed with the names above.

---

## 2. Store the Groq API key in Secrets Manager

Secrets Manager → **Store a new secret**.

1. Secret type: **Other type of secret**.
2. Key/value: key `GROQ_API_KEY`, value = your Groq key (type it directly in the console).
3. Secret name: `shopping-agent/groq` → Next → Next → **Store**.
4. Open the secret and copy its **Secret ARN**. It looks like `arn:aws:secretsmanager:us-east-1:763679488809:secret:shopping-agent/groq-AbC123`. You need it in steps 3 and 7.

Do not paste the key into chat, tickets or git. Confirm that storing it this way is allowed under WBD credential policy (GICS).

---

## 3. Let the task execution role read the secret

IAM → **Roles** → `ecsTaskExecutionRole` → **Add permissions** → **Create inline policy** → JSON:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": "secretsmanager:GetSecretValue",
    "Resource": "<SECRET_ARN_FROM_STEP_2>"
  }]
}
```

Name it `shopping-agent-read-secret` → **Create policy**.

`ecsTaskExecutionRole` is shared by other apps in this account; the policy only grants access to this one secret.

---

## 4. (Skipped) No EFS

Persistence is intentionally not used, so there is no EFS file system. The database is created at `/app/resources/store.db` on the task's temporary disk each time the container starts. Nothing to do in this step.

---

## 5. Create the CloudWatch log group

CloudWatch → **Log groups** → **Create log group**: name `/ecs/shopping-agent`, retention 14 days → **Create**.

---

## 6. Create the ECS cluster

ECS → **Clusters** → **Create cluster**.
- Name `shopping-agent`.
- Infrastructure: **AWS Fargate (serverless)** only.
- **Create**.

(The account also has `default` and `ess-dev-ecs-cluster`. Use a dedicated cluster so cleanup is simple.)

---

## 7. Create the task definition

ECS → **Task definitions** → **Create new task definition**.

**Task definition configuration**
- Family: `shopping-agent`
- Launch type: **AWS Fargate**
- OS/Architecture: **Linux/X86_64** (the GitHub Actions workflow builds `linux/amd64`)
- CPU `.5 vCPU`, Memory `1 GB`
- Task role: leave as **None**
- Task execution role: `ecsTaskExecutionRole`

**Container 1**
- Name `shopping-agent`
- Image URI: `763679488809.dkr.ecr.us-east-1.amazonaws.com/shopping-agent:f04d8225140967914877b36feddc08ab8f6ecb26`
- Essential container: Yes
- Port mappings: Container port `8501`, Protocol TCP, Port name `streamlit`, App protocol HTTP
- Environment variables: **Add environment variable** →
  - Key `GROQ_API_KEY`, Type **ValueFrom**, Value `<SECRET_ARN_FROM_STEP_2>:GROQ_API_KEY::`
  (the trailing `:GROQ_API_KEY::` selects the JSON key from the secret)
- Logging: **Use log collection** is on, driver `awslogs`, group `/ecs/shopping-agent`, region `us-east-1`, stream prefix `ecs`
- Leave the container health check empty. The image has no `curl`; the ALB does the health checking.

Do not add any volume or mount point (no persistence).

→ **Create**.

---

## 8. Create the target group

EC2 → **Target Groups** → **Create target group**.

1. Target type **IP addresses**.
2. Name `shopping-agent-tg`, Protocol HTTP, Port `8501`, VPC `vpc-0c6634cdfa0eab96f`, Protocol version HTTP1.
3. Health check: protocol HTTP, path `/_stcore/health`, success codes `200`. Under advanced settings you can set interval 30s and healthy threshold 2.
4. **Next**. Do not register any targets by hand (ECS registers the task). **Create target group**.
5. Open the target group → **Attributes** → **Edit** → turn on **Stickiness**, type **Load balancer generated cookie**, duration 1 day → **Save**.

Stickiness keeps a browser on the same task, which Streamlit's websocket and chat session need.

---

## 9. Create the load balancer

EC2 → **Load Balancers** → **Create load balancer** → **Application Load Balancer**.

- Name `shopping-agent-alb`, Scheme **Internet-facing**, IP type IPv4.
- Network mapping: VPC `vpc-0c6634cdfa0eab96f`; select all three **public** subnets (1a, 1b, 1c).
- Security group: `shopping-agent-alb-sg` only (remove the default).
- Listener: HTTP, port 80, default action **Forward to** `shopping-agent-tg`.
- **Create load balancer**. After it is created, open it → **Attributes** → **Edit** → **Idle timeout** `120` seconds → Save.
- Copy the **DNS name** (`shopping-agent-alb-....us-east-1.elb.amazonaws.com`).

---

## 10. Create the ECS service

ECS → Clusters → `shopping-agent` → **Services** → **Create**.

**Service details**
- Task definition family `shopping-agent`, latest revision. Service name `shopping-agent-svc`.

**Environment**
- Compute options: **Launch type**, Launch type **FARGATE**, Platform version **LATEST**.

**Deployment configuration**
- Scheduling strategy **Replica**, Desired tasks **1**.
- Deployment options: **Min running tasks 100%**, **Max running tasks 200%**. The new task starts and becomes healthy before the old one stops, so there is no downtime. Each task has its own database, so the new task starts with empty orders.
- Optional: turn on **Deployment failure detection → Use the Amazon ECS deployment circuit breaker** with **Rollback on failures**.

**Networking**
- VPC `vpc-0c6634cdfa0eab96f`.
- Subnets: select only the three **private** subnets; remove the others.
- Security group: use existing `shopping-agent-task-sg` (remove the default).
- Public IP: **Turned off**.

**Load balancing**
- Load balancer type **Application Load Balancer**, **Use an existing load balancer** → `shopping-agent-alb`.
- Container `shopping-agent 8501:8501`.
- Listener: use existing **80:HTTP**. Target group: use existing `shopping-agent-tg`.
- Health check grace period: `60` seconds.

→ **Create**.

---

## 11. Verify

1. ECS → cluster → service `shopping-agent-svc` → **Tasks**: the task goes `PROVISIONING` → `PENDING` → **`RUNNING`** (1–3 minutes). Service shows **1/1**.
2. EC2 → Target Groups → `shopping-agent-tg` → **Targets**: the IP shows **healthy**.
3. Open `http://<ALB DNS name>` in a browser. You should see the Fresh Cart page.
4. Ask: "Find organic honey under $20 with 4.5+ rating". You should get product results.
5. Check logs: CloudWatch → `/ecs/shopping-agent` → latest stream. You should see `Database created at: /app/resources/store.db` and the Streamlit "You can now view your Streamlit app" lines.
6. Expected behavior: orders are **not** kept. After a forced new deployment (ECS → service → **Update** → **Force new deployment**) the order list is empty again.

---

## 12. Deploy a new version of the app

1. Push to `main` on GitHub. The workflow builds and pushes a new image tagged with the commit SHA (check ECR for the tag).
2. ECS → **Task definitions** → `shopping-agent` → latest revision → **Create new revision** → change the container image tag to the new SHA → **Create**.
3. ECS → cluster → service → **Update** → select the new revision → **Update**.
4. Watch the task roll over and re-run the checks in section 11.

---

## 13. Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| Task stops with `CannotPullContainerError` | The task cannot reach ECR. Confirm it runs in the **private** subnets with a NAT route, and the image tag exists. |
| `ResourceInitializationError: unable to pull secrets` | Step 3 policy missing, wrong secret ARN, or the `:GROQ_API_KEY::` suffix is wrong. |
| `exec format error` in logs | Architecture mismatch. The task must be Linux/X86_64 to match the `linux/amd64` image. |
| Target group shows **unhealthy** | `shopping-agent-task-sg` must allow 8501 from the ALB group; health check path must be `/_stcore/health`; give the service a 60s grace period. |
| ALB returns 502/504 | Task not running or still starting; check the task and its logs. |
| Page loads but the chat disconnects or resets | Stickiness not enabled (step 8) or ALB idle timeout too low (step 9). |
| Agent replies with an error about the API key | The secret value or key name is wrong. The key name must be `GROQ_API_KEY`. |
| Orders or chat differ between page loads | More than one task is running, each with its own database. Set desired tasks to 1. |
| Orders disappeared | Expected: no persistence. The task restarted or was redeployed. |

---

## 14. Clean up (in this order)

1. ECS service `shopping-agent-svc`: **Delete** (force delete if needed).
2. Load balancer `shopping-agent-alb`: **Delete**; then target group `shopping-agent-tg`.
3. ECS cluster `shopping-agent`: **Delete**; deregister the task definition revisions if you want.
4. Secrets Manager `shopping-agent/groq`: **Delete** (7-day minimum recovery window), and remove the inline policy `shopping-agent-read-secret` from `ecsTaskExecutionRole`.
5. CloudWatch log group `/ecs/shopping-agent`.
6. Security groups `shopping-agent-task-sg`, then `shopping-agent-alb-sg`.

---

## Notes and limitations

- **HTTP only.** Traffic, including chat content, is not encrypted. For real use, add an ACM certificate and an HTTPS listener, and keep the ALB security group restricted to a known CIDR.
- **No persistence.** Orders are lost on every restart or deployment. To keep them later, add an EFS volume (single task) or move orders to RDS Postgres, which needs code changes in `src/tools.py` and `src/setup_db.py`.
- **Single task.** Run 1 task; a second task would have its own separate database.
- **Startup behavior.** The container runs `python src/setup_db.py` before Streamlit on every start, creating a fresh database each time.
- **Review before use.** All resource IDs above were read from the account on 2026-11-23; re-check them in the console if time has passed.
