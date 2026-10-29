variable "aws_region" {
  type = string
  default = "ap-southeast-1"
}
variable "state_bucket_name" {
  type = string
}
variable "github_owner" {
  type = string
  default = "chiendz11"
}
variable "infrastructure_repository" {
  type = string
  default = "Maint-infrastructure"
}
variable "existing_github_oidc_provider_arn" {
  type = string
  default = null
}
