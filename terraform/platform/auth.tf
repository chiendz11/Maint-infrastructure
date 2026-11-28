resource "aws_cognito_user_pool" "this" {
  name                     = "${local.name}-users"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  mfa_configuration        = "OPTIONAL"

  software_token_mfa_configuration {
    enabled = true
  }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 7
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_cognito_user_group" "roles" {
  for_each     = toset(["ADMIN", "OPERATOR", "TECHNICIAN", "VIEWER"])
  name         = each.value
  user_pool_id = aws_cognito_user_pool.this.id
  description  = "MaintAI RBAC role ${each.value}"
}

resource "aws_cognito_user_pool_domain" "this" {
  domain       = var.cognito_domain_prefix != "" ? var.cognito_domain_prefix : "${local.name}-${data.aws_caller_identity.current.account_id}"
  user_pool_id = aws_cognito_user_pool.this.id
}

resource "aws_cognito_resource_server" "api" {
  identifier   = "https://api.${data.terraform_remote_state.domain.outputs.domain_name}"
  name         = "${local.name}-apis"
  user_pool_id = aws_cognito_user_pool.this.id

  scope {
    scope_name        = "simulator:control"
    scope_description = "Control sensor simulator scenarios and replay"
  }
  scope {
    scope_name        = "processing:read"
    scope_description = "Read processing history and evidence delegation"
  }
  scope {
    scope_name        = "ml:predict"
    scope_description = "Invoke internal ML inference endpoints"
  }
  scope {
    scope_name        = "business:read"
    scope_description = "Access business fleet and alert projections"
  }
  scope {
    scope_name        = "rag:brief"
    scope_description = "Generate grounded maintenance briefs via internal RAG service"
  }
}

resource "aws_cognito_user_pool_client" "ui" {
  for_each                             = toset(["business-ui", "simulator-ui"])
  name                                 = "${local.name}-${each.value}"
  user_pool_id                         = aws_cognito_user_pool.this.id
  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "profile", "email"]
  supported_identity_providers         = ["COGNITO"]
  callback_urls = [
    each.key == "business-ui"
    ? "https://app.${data.terraform_remote_state.domain.outputs.domain_name}/callback"
    : "https://simulator.${data.terraform_remote_state.domain.outputs.domain_name}/callback"
  ]
  logout_urls = [
    each.key == "business-ui"
    ? "https://app.${data.terraform_remote_state.domain.outputs.domain_name}/"
    : "https://simulator.${data.terraform_remote_state.domain.outputs.domain_name}/"
  ]
}

resource "aws_cognito_user_pool_client" "m2m" {
  for_each = {
    processing      = ["${aws_cognito_resource_server.api.identifier}/processing:read", "${aws_cognito_resource_server.api.identifier}/ml:predict"]
    registry        = ["${aws_cognito_resource_server.api.identifier}/business:read"]
    ml              = ["${aws_cognito_resource_server.api.identifier}/ml:predict"]
    sensor          = ["${aws_cognito_resource_server.api.identifier}/simulator:control"]
    business-worker = ["${aws_cognito_resource_server.api.identifier}/rag:brief"]
  }
  name                                 = "${local.name}-m2m-${each.key}"
  user_pool_id                         = aws_cognito_user_pool.this.id
  generate_secret                      = true
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["client_credentials"]
  allowed_oauth_scopes                 = each.value
  supported_identity_providers         = ["COGNITO"]
}
