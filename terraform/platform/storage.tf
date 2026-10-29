resource "aws_kms_key" "data" {
  description             = "MaintAI datasets, model artifacts and training ledger"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  lifecycle { prevent_destroy = true }
}
resource "aws_kms_alias" "data" {
  name          = "alias/${local.name}-data"
  target_key_id = aws_kms_key.data.key_id
}
resource "aws_s3_bucket" "data" {
  for_each      = toset(["datasets", "artifacts", "raw", "knowledge"])
  bucket        = "${local.name}-${each.key}-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
  force_destroy = false
  lifecycle { prevent_destroy = true }
}
resource "aws_s3_bucket_versioning" "data" {
  for_each = aws_s3_bucket.data
  bucket   = each.value.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  for_each = aws_s3_bucket.data
  bucket   = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.data.arn
    }
    bucket_key_enabled = true
  }
}
resource "aws_s3_bucket_public_access_block" "data" {
  for_each                = aws_s3_bucket.data
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_policy" "data" {
  for_each = aws_s3_bucket.data
  bucket   = each.value.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Deny", Principal = "*", Action = "s3:*"
    Resource = [each.value.arn, "${each.value.arn}/*"]
    Condition = { Bool = { "aws:SecureTransport" = "false" } }
  }] })
}
resource "aws_sqs_queue" "dataset_dlq" {
  name                      = "${local.name}-dataset-events-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled    = true
}
resource "aws_sqs_queue" "dataset" {
  name                       = "${local.name}-dataset-events"
  message_retention_seconds  = 345600
  visibility_timeout_seconds = 300
  receive_wait_time_seconds  = 20
  max_message_size           = 262144
  sqs_managed_sse_enabled     = true
  redrive_policy = jsonencode({ deadLetterTargetArn = aws_sqs_queue.dataset_dlq.arn, maxReceiveCount = 5 })
}
resource "aws_sqs_queue_policy" "dataset" {
  queue_url = aws_sqs_queue.dataset.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Service = "s3.amazonaws.com" }, Action = "sqs:SendMessage"
    Resource = aws_sqs_queue.dataset.arn
    Condition = {
      ArnEquals = { "aws:SourceArn" = aws_s3_bucket.data["datasets"].arn }
      StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
    }
  }] })
}
resource "aws_s3_bucket_notification" "dataset" {
  bucket = aws_s3_bucket.data["datasets"].id
  queue {
    queue_arn     = aws_sqs_queue.dataset.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "datasets/approved/"
    filter_suffix = ".manifest.json"
  }
  depends_on = [aws_sqs_queue_policy.dataset, aws_s3_bucket_versioning.data]
}
resource "aws_dynamodb_table" "training" {
  name         = "${local.name}-training-ledger"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "training_id"
  attribute {
    name = "training_id"
    type = "S"
  }
  point_in_time_recovery { enabled = true }
  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.data.arn
  }
  deletion_protection_enabled = true
  lifecycle { prevent_destroy = true }
}
resource "aws_ecr_repository" "workload" {
  for_each             = local.components
  name                 = "${local.name}/${each.value}"
  image_tag_mutability = "IMMUTABLE_WITH_EXCLUSION"
  # Application version tags remain immutable. Cosign appends signatures/attestations
  # under metadata tags; those are never used as deployed image versions.
  image_tag_mutability_exclusion_filter {
    filter      = "sha256-*.sig"
    filter_type = "WILDCARD"
  }
  image_tag_mutability_exclusion_filter {
    filter      = "sha256-*.att"
    filter_type = "WILDCARD"
  }
  force_delete         = false
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "AES256" }
  lifecycle { prevent_destroy = true }
}
