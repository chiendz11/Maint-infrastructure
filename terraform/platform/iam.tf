locals {
  issuer = replace(aws_eks_cluster.this.identity[0].oidc[0].issuer, "https://", "")
  service_accounts = {
    external-secrets = "external-secrets:external-secrets"
    external-dns = "external-dns:external-dns"
    load-balancer = "kube-system:aws-load-balancer-controller"
    ebs-csi = "kube-system:ebs-csi-controller-sa"
    sqs-events = "argo-events:sqs-eventsource"
    training = "argo:maintai-training"
    automation = "argo:maintai-automation"
    mlflow = "maintai:mlflow"
    ml-service = "maintai:ml-service"
    drift-worker = "maintai:drift-worker"
    sensor = "maintai:sensor"
    storage-consumer = "maintai:storage-consumer"
    rag-service = "maintai:rag-service"
  }
}
resource "aws_iam_role" "workload" {
  for_each = local.service_accounts
  name = "${local.name}-${each.key}"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "sts:AssumeRoleWithWebIdentity"
    Principal = { Federated = aws_iam_openid_connect_provider.cluster.arn }
    Condition = { StringEquals = { "${local.issuer}:aud" = "sts.amazonaws.com", "${local.issuer}:sub" = "system:serviceaccount:${each.value}" } }
  }] })
}
resource "aws_iam_role_policy_attachment" "ebs" {
  role = aws_iam_role.workload["ebs-csi"].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}
resource "aws_iam_role_policy" "alb" {
  role = aws_iam_role.workload["load-balancer"].id
  policy = file("${path.module}/policies/aws-load-balancer-controller-v2.14.0.json")
}
resource "aws_iam_role_policy" "dns" {
  role = aws_iam_role.workload["external-dns"].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["route53:ChangeResourceRecordSets"], Resource = data.terraform_remote_state.domain.outputs.hosted_zone_arn },
    { Effect = "Allow", Action = ["route53:ListHostedZones", "route53:ListHostedZonesByName", "route53:ListResourceRecordSets", "route53:ListTagsForResource"], Resource = "*" }
  ] })
}
resource "aws_iam_role_policy" "secrets" {
  role = aws_iam_role.workload["external-secrets"].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"], Resource = concat([for secret in aws_secretsmanager_secret.runtime : secret.arn], [aws_db_instance.this.master_user_secret[0].secret_arn], tolist(var.additional_external_secret_arns)) },
    { Effect = "Allow", Action = ["kms:Decrypt", "kms:DescribeKey"], Resource = aws_kms_key.data.arn }
  ] })
}
resource "aws_iam_role_policy" "sqs" {
  role = aws_iam_role.workload["sqs-events"].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility", "sqs:GetQueueAttributes", "sqs:GetQueueUrl"], Resource = aws_sqs_queue.dataset.arn }] })
}
locals {
  s3_grants = {
    sensor = { read = ["${aws_s3_bucket.data["datasets"].arn}/simulator/*"], write = [] }
    ml-service = { read = ["${aws_s3_bucket.data["artifacts"].arn}/models/*"], write = [] }
    drift-worker = { read = ["${aws_s3_bucket.data["datasets"].arn}/curated/*", "${aws_s3_bucket.data["artifacts"].arn}/models/*"], write = ["${aws_s3_bucket.data["artifacts"].arn}/drift-reports/*"] }
    storage-consumer = { read = ["${aws_s3_bucket.data["raw"].arn}/raw-sensor/*"], write = ["${aws_s3_bucket.data["raw"].arn}/raw-sensor/*"] }
    rag-service = { read = ["${aws_s3_bucket.data["knowledge"].arn}/manuals/*"], write = [] }
    training = { read = ["${aws_s3_bucket.data["datasets"].arn}/datasets/*", "${aws_s3_bucket.data["datasets"].arn}/curated/*", "${aws_s3_bucket.data["artifacts"].arn}/models/*"], write = ["${aws_s3_bucket.data["artifacts"].arn}/models/*", "${aws_s3_bucket.data["artifacts"].arn}/training/*"] }
    automation = { read = ["${aws_s3_bucket.data["datasets"].arn}/datasets/*", "${aws_s3_bucket.data["artifacts"].arn}/models/*", "${aws_s3_bucket.data["artifacts"].arn}/training/*"], write = ["${aws_s3_bucket.data["artifacts"].arn}/training/*"] }
    mlflow = { read = ["${aws_s3_bucket.data["artifacts"].arn}/mlflow/*"], write = ["${aws_s3_bucket.data["artifacts"].arn}/mlflow/*"] }
  }
}
resource "aws_iam_role_policy" "s3" {
  for_each = local.s3_grants
  role = aws_iam_role.workload[each.key].id
  policy = jsonencode({ Version = "2012-10-17", Statement = concat([
    { Effect = "Allow", Action = ["s3:GetObject", "s3:GetObjectVersion"], Resource = each.value.read },
    { Effect = "Allow", Action = ["kms:Decrypt", "kms:DescribeKey"], Resource = aws_kms_key.data.arn }
  ], length(each.value.write) == 0 ? [] : [
    { Effect = "Allow", Action = ["s3:PutObject"], Resource = each.value.write },
    { Effect = "Allow", Action = ["kms:Encrypt", "kms:GenerateDataKey"], Resource = aws_kms_key.data.arn }
  ]) })
}
resource "aws_iam_role_policy" "mlflow_list" {
  role = aws_iam_role.workload["mlflow"].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.data["artifacts"].arn, Condition = { StringLike = { "s3:prefix" = ["mlflow", "mlflow/*"] } } }] })
}
resource "aws_iam_role_policy" "training_ledger" {
  for_each = toset(["training", "automation"])
  role = aws_iam_role.workload[each.value].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"], Resource = aws_dynamodb_table.training.arn }] })
}
locals {
  publishers = {
    app = { repository = var.app_repository, components = ["ingestion-api", "processing", "business-backend", "storage-consumer", "ml-service", "training", "rag-service", "frontend", "simulator-ui", "sensor", "drift-worker"] }
    gitops = { repository = var.gitops_repository, components = ["automation", "mlflow"] }
  }
}
resource "aws_iam_role" "publisher" {
  for_each = local.publishers
  name = "${local.name}-${each.key}-publisher"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRoleWithWebIdentity", Principal = { Federated = var.github_oidc_provider_arn }, Condition = { StringEquals = { "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com", "token.actions.githubusercontent.com:sub" = "repo:${var.github_owner}/${each.value.repository}:environment:prod" } } }] })
}
resource "aws_iam_role_policy" "publisher" {
  for_each = local.publishers
  role = aws_iam_role.publisher[each.key].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
    { Effect = "Allow", Action = ["ecr:BatchCheckLayerAvailability", "ecr:CompleteLayerUpload", "ecr:GetDownloadUrlForLayer", "ecr:InitiateLayerUpload", "ecr:PutImage", "ecr:UploadLayerPart", "ecr:BatchGetImage", "ecr:DescribeImages"], Resource = [for component in each.value.components : aws_ecr_repository.workload[component].arn] }
  ] })
}
resource "aws_iam_role" "gitops_reader" {
  name = "${local.name}-gitops-reader"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRoleWithWebIdentity", Principal = { Federated = var.github_oidc_provider_arn }, Condition = { StringEquals = { "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com", "token.actions.githubusercontent.com:sub" = "repo:${var.github_owner}/${var.gitops_repository}:ref:refs/heads/main" } } }] })
}
resource "aws_iam_role_policy" "gitops_reader" {
  role = aws_iam_role.gitops_reader.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["s3:GetObjectVersion"], Resource = ["${aws_s3_bucket.data["artifacts"].arn}/models/*", "${aws_s3_bucket.data["artifacts"].arn}/training/*"] },
    { Effect = "Allow", Action = ["kms:Decrypt"], Resource = aws_kms_key.data.arn },
    { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
    { Effect = "Allow", Action = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:DescribeImages"], Resource = [for repo in aws_ecr_repository.workload : repo.arn] }
  ] })
}

resource "aws_iam_role" "dataset_publisher" {
  name = "${local.name}-dataset-publisher"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRoleWithWebIdentity", Principal = { Federated = var.github_oidc_provider_arn }, Condition = { StringEquals = { "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com", "token.actions.githubusercontent.com:sub" = "repo:${var.github_owner}/${var.app_repository}:environment:prod" } } }] })
}
resource "aws_iam_role_policy" "dataset_publisher" {
  role = aws_iam_role.dataset_publisher.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["s3:PutObject", "s3:GetObjectVersion"], Resource = ["${aws_s3_bucket.data["datasets"].arn}/datasets/*", "${aws_s3_bucket.data["datasets"].arn}/curated/*"] },
    { Effect = "Allow", Action = ["sqs:SendMessage"], Resource = aws_sqs_queue.dataset.arn },
    { Effect = "Allow", Action = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"], Resource = aws_kms_key.data.arn }
  ] })
}
