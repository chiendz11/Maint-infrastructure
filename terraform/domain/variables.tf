variable "aws_region" {
  type = string
  default = "ap-southeast-1"
}
variable "domain_name" {
  type = string
}
variable "existing_hosted_zone_id" {
  type = string
  default = null
}
variable "wait_for_certificate_validation" {
  type = bool
  default = false
}
