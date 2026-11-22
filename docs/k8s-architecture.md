# Kubernetes architecture (as deployed)

![Kubernetes architecture](k8s-architecture.svg)

```mermaid
flowchart LR
    U([User browser<br/>localhost:8503]) -->|kubectl port-forward| SVC
    subgraph C["Cluster: docker-desktop (nodes: control-plane, worker)"]
        SVC["Service shopping-agent<br/>NodePort 30080, 80 to 8501<br/>sessionAffinity ClientIP"]
        subgraph D["Deployment shopping-agent: 2 replicas, Recreate"]
            P1["Pod 1<br/>Streamlit + LangChain agent"]
            P2["Pod 2<br/>Streamlit + LangChain agent"]
        end
        SEC["Secret shopping-agent-env<br/>GROQ API key"] -->|envFrom| D
        PVC[("PVC shopping-agent-data<br/>1Gi RWO<br/>/app/resources/store.db")]
        P1 --> PVC
        P2 --> PVC
        SVC --> P1
        SVC --> P2
    end
    P1 & P2 -.->|HTTPS egress| G["GroqCloud<br/>gpt-oss-120b"]
```

Source of truth: `k8s/deployment.yaml` and `k8s/KUBERNETES_SETUP.md`.
Note the shared SQLite volume across 2 replicas (risk of "database is locked").

*Created using Anthropic Claude. Keep on internal versions until a human has reviewed and verified the content.*
