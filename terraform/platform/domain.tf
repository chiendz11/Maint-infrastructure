data "terraform_remote_state" "domain" {
  backend = "s3"
  config = { bucket = var.state_bucket, key = "maintai-v13/domain.tfstate", region = var.aws_region, encrypt = true, kms_key_id = var.state_kms_key_arn }
}
