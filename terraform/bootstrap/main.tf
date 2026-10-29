locals { name = "maintai-v13-production" }
resource "aws_kms_key" "state" {
  description = "MaintAI Terraform state"
  enable_key_rotation = true
  deletion_window_in_days = 30
  lifecycle { prevent_destroy = true }
}
resource "aws_s3_bucket" "state" {
  bucket = var.state_bucket_name
  lifecycle { prevent_destroy = true }
}
resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id
  block_public_acls = true
  block_public_policy = true
  ignore_public_acls = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
      kms_master_key_id = aws_kms_key.state.arn
    }
    bucket_key_enabled = true
  }
}
resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Deny", Principal = "*", Action = "s3:*", Resource = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"], Condition = { Bool = { "aws:SecureTransport" = "false" } } }] })
}
resource "aws_iam_openid_connect_provider" "github" {
  count = var.existing_github_oidc_provider_arn == null ? 1 : 0
  url = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}
locals {
  oidc_arn = var.existing_github_oidc_provider_arn != null ? var.existing_github_oidc_provider_arn : aws_iam_openid_connect_provider.github[0].arn
  subjects = { plan = "repo:${var.github_owner}/${var.infrastructure_repository}:pull_request", apply = "repo:${var.github_owner}/${var.infrastructure_repository}:environment:prod" }
}
resource "aws_iam_role" "terraform" {
  for_each = local.subjects
  name = "${local.name}-${each.key}"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRoleWithWebIdentity", Principal = { Federated = local.oidc_arn }, Condition = { StringEquals = { "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com", "token.actions.githubusercontent.com:sub" = each.value } } }] })
}
resource "aws_iam_role_policy_attachment" "plan" {
  role = aws_iam_role.terraform["plan"].name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}
# Bootstrap privilege: scope with a reviewed permissions boundary before shared-team use.
resource "aws_iam_role_policy_attachment" "apply" {
  role = aws_iam_role.terraform["apply"].name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}
resource "aws_iam_role_policy" "state" {
  for_each = aws_iam_role.terraform
  role = each.value.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.state.arn },
    { Effect = "Allow", Action = ["s3:GetObject"], Resource = "${aws_s3_bucket.state.arn}/maintai-v13/*" },
    { Effect = "Allow", Action = ["s3:PutObject"], Resource = each.key == "apply" ? "${aws_s3_bucket.state.arn}/maintai-v13/*" : "${aws_s3_bucket.state.arn}/maintai-v13/*.tflock" },
    { Effect = "Allow", Action = ["s3:DeleteObject"], Resource = "${aws_s3_bucket.state.arn}/maintai-v13/*.tflock" },
    { Effect = "Allow", Action = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey", "kms:DescribeKey"], Resource = aws_kms_key.state.arn }
  ] })
}
output "state_bucket" { value = aws_s3_bucket.state.id }
output "state_kms_key_arn" { value = aws_kms_key.state.arn }
output "github_oidc_provider_arn" { value = local.oidc_arn }
output "plan_role_arn" { value = aws_iam_role.terraform["plan"].arn }
output "apply_role_arn" { value = aws_iam_role.terraform["apply"].arn }
