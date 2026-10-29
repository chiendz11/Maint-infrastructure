# Reference sources and adaptations

Main reference snapshots retrieved on 2026-10-18:

- [iris-gitops](https://github.com/chiendz11/iris-gitops/tree/ed951731ce378a6468bf01e4bb80376b8e39872a)
- [iris-infrastructure](https://github.com/chiendz11/iris-infrastructure/tree/6c661a6eee543ac23dd9d998ceef59b3e3804929)

The user's second URL duplicated iris-gitops with a trailing comma; infrastructure
reference follows the earlier named iris-infrastructure repository. Existing local
Iris checkouts had unrelated modifications, so clean main clones in /tmp were used
for reference without changing them. Some foundational Terraform/IAM patterns and
provider locks were adapted from the earlier local underscore drafts; no actual
secret files, state, datasets, user modifications or application trainer were copied.

Official documentation consulted for implementation design:

- [Strimzi 0.47 deployment/configuration](https://strimzi.io/docs/operators/0.47.0/deploying)
- [AWS provider 6.61.0 EKS resource](https://registry.terraform.io/providers/hashicorp/aws/6.61.0/docs/resources/eks_cluster)
- [Argo Events Workflow trigger](https://argoproj.github.io/argo-events/sensors/triggers/argo-workflow/)
- [Argo Workflows specification](https://argo-workflows.readthedocs.io/en/latest/fields/)

New code adapts lifecycle boundaries to MaintAI native HTTP prediction, Kafka
processing/business groups, five DB owners and separate Simulator UI. It does not
copy Iris's KServe prediction protocol or claim Iris runtime validation applies.
